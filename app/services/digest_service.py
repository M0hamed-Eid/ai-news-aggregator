# app/services/digest_service.py
#
# DigestService: orchestrates the full "generate + curate + email" pipeline.
#
# Why this service exists
# -----------------------
# The three agents (DigestAgent, CuratorAgent, EmailAgent) each do one job.
# Someone has to drive them in sequence and handle the database I/O between
# steps.  Putting that logic in run_pipeline.py would make it a monolith; a
# dedicated service keeps concerns separated and makes the pipeline easy to
# test and extend (e.g. scheduling, retries, dry-run mode).
#
# Responsibility breakdown
# ------------------------
# 1. Fetch unsummarised records from the DB (via repositories).
# 2. Call DigestAgent to generate title + summary for each record.
# 3. Persist the summaries back to the DB.
# 4. Fetch ALL recent records (summarised or not) for ranking.
# 5. Call CuratorAgent to rank them.
# 6. Call EmailAgent to build the final EmailDigestResponse.
# 7. Return the response to the caller (run_pipeline.py, a scheduler, etc.).

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Union

from app.agents.curator_agent import CuratorAgent
from app.agents.digest_agent import DigestAgent
from app.agents.email_agent import EmailAgent, EmailDigestResponse
from app.config import AppConfig
from app.database import (
    ArticleRepository,
    YoutubeRepository,
    get_db_session,
)
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result summary
# ---------------------------------------------------------------------------

@dataclass
class DigestServiceResult:
    articles_summarised: int = 0
    videos_summarised: int = 0
    total_ranked: int = 0
    digest_response: Optional[EmailDigestResponse] = None
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.digest_response is not None and not self.errors


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DigestService:
    """
    Orchestrates DigestAgent → CuratorAgent → EmailAgent in sequence,
    reading from and writing to the database via the repository layer.

    Parameters
    ----------
    config       : AppConfig instance (provides UserProfile + ScraperConfig)
    hours_window : how far back to look when fetching content for ranking
    top_n        : how many articles to include in the final digest
    dry_run      : if True, skip all DB writes and return a response based
                   on already-summarised records only
    """

    def __init__(
        self,
        config: AppConfig,
        hours_window: int = 144,
        top_n: int = 10,
        dry_run: bool = False,
    ) -> None:
        self._config = config
        self._hours_window = hours_window
        self._top_n = top_n
        self._dry_run = dry_run

        self._digest_agent = DigestAgent()
        self._curator_agent = CuratorAgent(config.user)
        self._email_agent = EmailAgent(config.user)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> DigestServiceResult:
        result = DigestServiceResult()

        # ── Step 1: Generate summaries for unsummarised records ──────────
        if not self._dry_run:
            art_count, vid_count, errors = self._summarise_unsummarised()
            result.articles_summarised = art_count
            result.videos_summarised = vid_count
            result.errors.extend(errors)

        # ── Step 2: Fetch recent content for ranking ─────────────────────
        items: List[Union[Article, YoutubeVideo]] = []
        try:
            with get_db_session() as db:
                items += ArticleRepository(db).get_recent(hours=self._hours_window)
                items += YoutubeRepository(db).get_recent(hours=self._hours_window)
        except Exception as exc:
            msg = f"DigestService: failed to fetch recent content — {exc}"
            logger.error(msg, exc_info=True)
            result.errors.append(msg)
            return result

        if not items:
            logger.warning(
                "DigestService: no content found in the last %d hours", self._hours_window
            )
            return result

        logger.info("DigestService: ranking %d items", len(items))

        # ── Step 3: Rank ─────────────────────────────────────────────────
        ranked = self._curator_agent.rank_items(items)
        result.total_ranked = len(ranked)

        if not ranked:
            msg = "DigestService: CuratorAgent returned no ranked items"
            logger.warning(msg)
            result.errors.append(msg)
            return result

        # ── Step 4: Build email digest ────────────────────────────────────
        try:
            result.digest_response = self._email_agent.build_response(
                ranked_scores=ranked,
                all_items=items,
                limit=self._top_n,
            )
        except Exception as exc:
            msg = f"DigestService: EmailAgent failed — {exc}"
            logger.error(msg, exc_info=True)
            result.errors.append(msg)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _summarise_unsummarised(
        self,
    ) -> tuple[int, int, List[str]]:
        """
        Pull unsummarised records from the DB, generate summaries, persist.

        Returns (articles_summarised, videos_summarised, error_messages).
        """
        art_count = vid_count = 0
        errors: List[str] = []

        # Articles
        try:
            with get_db_session() as db:
                repo = ArticleRepository(db)
                unsummarised_articles: List[Article] = repo.get_unsummarised()
                for article in unsummarised_articles:
                    digest = self._digest_agent.digest_article(article)
                    if digest is None:
                        logger.warning(
                            "DigestService: no digest generated for article id=%d", article.id
                        )
                        continue
                    if repo.update_summary(article.id, digest.summary):
                        art_count += 1
        except Exception as exc:
            msg = f"DigestService: article summarisation failed — {exc}"
            logger.error(msg, exc_info=True)
            errors.append(msg)

        # Videos
        try:
            with get_db_session() as db:
                repo_v = YoutubeRepository(db)
                unsummarised_videos: List[YoutubeVideo] = repo_v.get_unsummarised()
                for video in unsummarised_videos:
                    digest = self._digest_agent.digest_video(video)
                    if digest is None:
                        logger.warning(
                            "DigestService: no digest generated for video id=%d", video.id
                        )
                        continue
                    if repo_v.update_summary(video.id, digest.summary):
                        vid_count += 1
        except Exception as exc:
            msg = f"DigestService: video summarisation failed — {exc}"
            logger.error(msg, exc_info=True)
            errors.append(msg)

        logger.info(
            "DigestService: summarised %d articles, %d videos", art_count, vid_count
        )
        return art_count, vid_count, errors