# app/services/digest_service.py
#
# DigestService: orchestrates the full "generate + curate + email" pipeline.
#
# Why this service exists
# -----------------------
# The three agents (EnrichmentAgent, CuratorAgent, EmailAgent) each do one
# job. Someone has to drive them in sequence and handle the database I/O
# between steps. Putting that logic in run_pipeline.py would make it a
# monolith; a dedicated service keeps concerns separated and makes the
# pipeline easy to test and extend (e.g. scheduling, retries, dry-run mode).
#
# Responsibility breakdown
# ------------------------
# 1. Fetch unenriched records from the DB (via repositories).
# 2. Call EnrichmentAgent's single structured LLM call per record — summary,
#    content_category, technical_depth, structured fields, why_it_matters,
#    topics, entities.
# 3. Persist across Article/YoutubeVideo.summary + content_enrichment +
#    content_topics + content_entities, and re-embed immediately.
# 4. Fetch ALL recent records (enriched or not) for ranking.
# 5. Call CuratorAgent to rank them.
# 6. Call EmailAgent to build the final EmailDigestResponse.
# 7. Return the response to the caller (run_pipeline.py, a scheduler, etc.).
#
# M8 — Content Intelligence Layer (2026-07-15)
# ----------------------------------------------
# Replaced DigestAgent (title+summary only) with EnrichmentAgent (Principle
# 4: ONE structured LLM call per item, everything downstream milestones
# need). `_summarise_unsummarised()` is now `_enrich_unenriched()` — driven
# by `get_unenriched()` (checks content_enrichment existence), NOT the old
# `get_unsummarised()` (checked `summary IS NULL`), since every pre-M8 row
# already has a summary but zero content_enrichment rows; the old check
# would have silently skipped the entire backfill corpus forever.

# app/services/digest_service.py
#
# DigestService: orchestrates the full "generate + curate + email" pipeline.
#
# Fixes from previous version
# ----------------------------------
# 1. BUG FIX: digest_response was never assigned to result — the service
#    built the email digest but then returned result.digest_response = None,
#    causing run_pipeline.py to log "No digest generated" every time.
#    Fixed by building the EmailDigestResponse inside the session block and
#    assigning it before returning.
#
# 2. BUG FIX: get_unsummarised(limit=20) was silently skipping older records.
#    Raised the default limit to 200 so all unsummarised content is processed
#    regardless of how many items are in the DB.
#
# 3. BUG FIX: Removed the duplicate DB fetch in Step 4. Previously the service
#    fetched items twice (once for ranking, once for email) and discarded the
#    second result. Now a single fetch is done, DigestItems are built from it
#    inside the session, and a url_map is stored so EmailAgent can attach
#    real URLs to the ranked articles.
#
# 4. Added url_map: digest_id → url so RankedArticleDetail.url is always
#    populated correctly (previously it was always empty string "").
#
# 5. MULTI-USER MILESTONE (2026-07-12): Ranking + email building are no
#    longer bound to one global config.user. Content is still fetched and
#    summarised exactly ONCE (ingestion/summarisation stay global, per the
#    "content collected once" requirement) — but Steps 3+4 now loop over
#    every active, non-paused recipient (app/services/recipients.py), each
#    getting their own CuratorAgent/EmailAgent instance (cheap to construct;
#    no internal refactor of those agents was needed) and their own filtered
#    content pool (category/source exclusions applied before ranking, so an
#    excluded source never reaches that user's LLM prompt at all). Result:
#    DigestServiceResult.digest_response (singular) is now digest_responses
#    (one RecipientDigest per user who got a digest this run).

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from app.agents.curator_agent import CuratorAgent, DigestItem
from app.agents.enrichment_agent import ENRICHMENT_VERSION, EnrichmentAgent, EnrichmentOutput
from app.agents.email_agent import EmailAgent, EmailDigestResponse
from app.config import AppConfig
from app.database import (
    ArticleRepository,
    YoutubeRepository,
    get_db_session,
)
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo
from app.database.repositories.content_entity_repository import ContentEntityRepository
from app.database.repositories.content_enrichment_repository import ContentEnrichmentRepository
from app.database.repositories.content_topic_repository import ContentTopicRepository
from app.database.repositories.digest_click_token_repository import DigestClickTokenRepository
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.taxonomy_topic_repository import TaxonomyTopicRepository
from app.database.repositories.user_ranking_repository import UserRankingRepository
from app.embeddings.embedding_service import embed_text
from app.services.recipients import Recipient, get_active_recipients, get_source_categories

from app.utils.reading_time import estimate_reading_minutes, estimate_watch_minutes
from app.utils.youtube import youtube_thumbnail_url

logger = logging.getLogger(__name__)

# Raise this if you have a very large DB — set to None for no limit
_SUMMARISE_BATCH_LIMIT = None

# Base URL of the Django web app — used to build tracked digest-click
# redirect links (M7). Read directly via os.getenv (not python-dotenv here)
# since load_dotenv() already ran at the entry point (run_pipeline.py /
# app/celery_app.py) before this module is ever imported.
_DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


# ---------------------------------------------------------------------------
# Result summary
# ---------------------------------------------------------------------------

@dataclass
class RecipientDigest:
    """One recipient's finished digest email, ready to send."""
    recipient: Recipient
    response: EmailDigestResponse


@dataclass
class DigestServiceResult:
    articles_summarised: int = 0
    videos_summarised: int = 0
    total_ranked: int = 0
    digest_responses: List[RecipientDigest] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.digest_responses) and not self.errors


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DigestService:
    """
    Orchestrates EnrichmentAgent → [CuratorAgent → EmailAgent, once per
    active recipient] in sequence, reading from and writing to the database
    via the repository layer.

    Parameters
    ----------
    config       : AppConfig instance (infra settings only — no per-user data
                   lives here anymore, see app/config.py's changelog)
    hours_window : how far back to look when fetching content for ranking
    top_n        : fallback per-digest article limit, used only for the
                   zero-active-users fallback recipient (see
                   app/services/recipients.py); real users' own
                   UserDigestSettings.max_items takes precedence
    dry_run      : if True, skip all DB writes and return a response based
                   on already-summarised records only
    enrichment_version : tag persisted to content_enrichment.enrichment_version
                   for every row this run writes — defaults to the current
                   prompt version (ENRICHMENT_VERSION), override for a
                   distinctly-tagged pass (e.g. an Ollama backfill run —
                   see app/database/backfill_enrichment.py).
    """

    def __init__(
        self,
        config: AppConfig,
        hours_window: int = 144,
        top_n: int = 10,
        dry_run: bool = False,
        enrichment_version: str = ENRICHMENT_VERSION,
    ) -> None:
        self._config = config
        self._hours_window = hours_window
        self._top_n = top_n
        self._dry_run = dry_run
        self._enrichment_version = enrichment_version

        # EnrichmentAgent is NOT constructed here — it needs the live
        # taxonomy_topics vocabulary (a DB read) to validate LLM-returned
        # topic slugs against, so _enrich_unenriched() builds it once per
        # run instead. CuratorAgent/EmailAgent are similarly constructed
        # fresh per recipient in run() — cheap (an LLM client handle + a
        # prompt string), no benefit to binding one shared instance globally.

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> DigestServiceResult:
        result = DigestServiceResult()

        # ── Step 1: Enrich unenriched records (summary + M8 structured fields) ──
        if not self._dry_run:
            art_count, vid_count, errors = self._enrich_unenriched()
            result.articles_summarised = art_count
            result.videos_summarised = vid_count
            result.errors.extend(errors)

        # ── Step 2: Fetch recent content + build DigestItems ─────────────
        # Do this inside the session so ORM attributes are accessible.
        # We also capture the url_map here so EmailAgent gets real URLs.
        digest_items: List[DigestItem] = []
        content_meta: Dict[str, dict] = {}  # digest_id → {url, image_url, reading_minutes}

        try:
            with get_db_session() as db:
                articles = ArticleRepository(db).get_recent(hours=self._hours_window)
                videos = YoutubeRepository(db).get_recent(hours=self._hours_window)
                combined: List[Union[Article, YoutubeVideo]] = articles + videos

                if not combined:
                    logger.warning(
                        "DigestService: no content found in the last %d hours",
                        self._hours_window,
                    )
                    return result

                # Build DigestItems while the session is still open. This is
                # a plain static conversion (ORM -> flat view-model), shared
                # across every recipient — no profile input needed here.
                digest_items = CuratorAgent.build_digest_items(combined)

                # Build url_map: digest_id → url (while ORM objects are attached)
                for item in combined:
                    if isinstance(item, Article):
                        key = f"{item.source}:{item.id}"
                        content_meta[key] = {
                            "url": item.url,
                            "image_url": item.image_url,
                            "reading_minutes": estimate_reading_minutes(len((item.content or "").split())),
                        }
                    else:
                        key = f"youtube:{item.id}"
                        content_meta[key] = {
                            "url": item.url,
                            "image_url": youtube_thumbnail_url(item.video_id) if item.video_id else None,
                            "reading_minutes": estimate_watch_minutes(len((item.content or "").split())),
                        }

        except Exception as exc:
            msg = f"DigestService: failed to fetch recent content — {exc}"
            logger.error(msg, exc_info=True)
            result.errors.append(msg)
            return result

        logger.info("DigestService: %d items available for ranking", len(digest_items))

        # ── Step 3: Look up recipients + per-source categories (for
        # exclusion filtering) — one query each, not per-recipient. ────────
        try:
            with get_db_session() as db:
                recipients = get_active_recipients(db)
                source_categories = get_source_categories(db)
        except Exception as exc:
            msg = f"DigestService: failed to load recipients — {exc}"
            logger.error(msg, exc_info=True)
            result.errors.append(msg)
            return result

        if not recipients:
            msg = "DigestService: no recipients found (no active users and no fallback configured)"
            logger.warning(msg)
            result.errors.append(msg)
            return result

        logger.info("DigestService: building digests for %d recipient(s)", len(recipients))

        # ── Step 4: Rank + build an email per recipient ───────────────────
        # Content is fetched/summarised ONCE above (shared, global) — only
        # ranking and email-building are per-user, using each recipient's own
        # profile and content-pool exclusions.
        for recipient in recipients:
            filtered_items = [
                d for d in digest_items
                if d.article_type not in recipient.excluded_sources
                and source_categories.get(d.article_type) not in recipient.excluded_categories
            ]
            if not filtered_items:
                logger.info(
                    "DigestService: nothing left for %s after exclusion filtering, skipping",
                    recipient.profile.email,
                )
                continue

            ranked = CuratorAgent(recipient.profile).rank_digests(filtered_items)
            result.total_ranked += len(ranked)

            if not ranked:
                msg = f"DigestService: CuratorAgent returned no ranked items for {recipient.profile.email}"
                logger.warning(msg)
                result.errors.append(msg)
                continue

            item_map = {d.digest_id: d for d in filtered_items}

            # Persist the ranking for the web app's personalized feed (Django
            # never re-ranks — it only ever reads this table). Real Django
            # users only; the zero-active-users fallback recipient has no
            # user_id and nothing to persist against.
            if recipient.user_id is not None:
                try:
                    with get_db_session() as db:
                        UserRankingRepository(db).replace_for_user(recipient.user_id, ranked, item_map)
                except Exception as exc:
                    logger.error(
                        "DigestService: failed to persist ranking for user_id=%s — %s",
                        recipient.user_id, exc, exc_info=True,
                    )

            # ── Digest click tokens (M7): tracked redirect links so digest
            # CTR is measurable. Tokens are minted ONLY for the items that
            # actually make this recipient's email (ranked[:limit] — the same
            # slice EmailAgent.build_response_with_urls() applies internally,
            # replicated here so we never mint a token for an item that gets
            # cut), and ONLY for real Django users — the zero-active-users
            # fallback recipient has no user_id to attribute a click to, so
            # it always gets the original (untracked) content_meta.
            recipient_content_meta = content_meta
            if recipient.user_id is not None:
                token_targets: List[tuple[str, int, str]] = []  # (content_type, content_id, digest_id)
                for r in ranked[: recipient.max_items]:
                    digest = item_map.get(r.digest_id)
                    if digest is None:
                        continue
                    content_type = "youtube_video" if digest.article_type == "youtube" else "article"
                    token_targets.append((content_type, digest.db_id, r.digest_id))

                if token_targets:
                    try:
                        with get_db_session() as db:
                            token_map = DigestClickTokenRepository(db).mint_for_recipient(
                                recipient.user_id,
                                [(content_type, content_id) for content_type, content_id, _ in token_targets],
                            )
                        # Shallow-copy per recipient — content_meta is shared
                        # across every recipient in this loop; mutating it in
                        # place would leak one recipient's token URL into the
                        # next recipient's email for the same shared item.
                        recipient_content_meta = dict(content_meta)
                        for content_type, content_id, digest_id in token_targets:
                            token = token_map.get((content_type, content_id))
                            if token and digest_id in recipient_content_meta:
                                overridden = dict(content_meta[digest_id])
                                overridden["url"] = f"{_DJANGO_BASE_URL}/r/{token}/"
                                recipient_content_meta[digest_id] = overridden
                    except Exception as exc:
                        logger.error(
                            "DigestService: failed to mint digest click tokens for user_id=%s — %s "
                            "(falling back to untracked URLs for this recipient)",
                            recipient.user_id, exc, exc_info=True,
                        )
                        recipient_content_meta = content_meta

            try:
                response = EmailAgent(recipient.profile).build_response_with_urls(
                    ranked_scores=ranked,
                    all_items=filtered_items,
                    content_meta=recipient_content_meta,
                    limit=recipient.max_items,
                )
                result.digest_responses.append(RecipientDigest(recipient=recipient, response=response))
            except Exception as exc:
                msg = f"DigestService: EmailAgent failed for {recipient.profile.email} — {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _enrich_unenriched(
        self,
        limit: Optional[int] = None,
    ) -> tuple[int, int, List[str]]:
        """
        Pull unenriched records from the DB, run EnrichmentAgent's single
        structured LLM call, persist across Article/YoutubeVideo.summary +
        content_enrichment + content_topics + content_entities, and
        re-embed immediately.

        `limit` overrides _SUMMARISE_BATCH_LIMIT — used by
        app/database/backfill_enrichment.py to run small, controlled
        batches rather than the whole corpus in one call.

        Returns (articles_enriched, videos_enriched, error_messages).
        """
        art_count = vid_count = 0
        errors: List[str] = []
        batch_limit = limit if limit is not None else _SUMMARISE_BATCH_LIMIT

        with get_db_session() as db:
            allowed_topics = TaxonomyTopicRepository(db).get_active_slugs()
        agent = EnrichmentAgent(allowed_topics=allowed_topics)

        # Articles — raised limit so older records aren't silently skipped
        try:
            with get_db_session() as db:
                repo = ArticleRepository(db)
                unenriched_articles: List[Article] = repo.get_unenriched(
                    limit=batch_limit
                )
                logger.info(
                    "DigestService: found %d unenriched articles",
                    len(unenriched_articles),
                )
                for article in unenriched_articles:
                    output = agent.enrich_article(article)
                    if output is None:
                        logger.warning(
                            "DigestService: no enrichment generated for article id=%d",
                            article.id,
                        )
                        continue
                    if repo.update_summary(article.id, output.summary):
                        art_count += 1
                    self._persist_enrichment(db, "article", article.id, output)
                    self._reembed(db, "article", article.id, output.summary)
        except Exception as exc:
            msg = f"DigestService: article enrichment failed — {exc}"
            logger.error(msg, exc_info=True)
            errors.append(msg)

        # Videos — raised limit so older records aren't silently skipped
        try:
            with get_db_session() as db:
                repo_v = YoutubeRepository(db)
                unenriched_videos: List[YoutubeVideo] = repo_v.get_unenriched(
                    limit=batch_limit
                )
                logger.info(
                    "DigestService: found %d unenriched videos",
                    len(unenriched_videos),
                )
                for video in unenriched_videos:
                    output = agent.enrich_video(video)
                    if output is None:
                        logger.warning(
                            "DigestService: no enrichment generated for video id=%d",
                            video.id,
                        )
                        continue
                    if repo_v.update_summary(video.id, output.summary):
                        vid_count += 1
                    self._persist_enrichment(db, "youtube_video", video.id, output)
                    self._reembed(db, "youtube_video", video.id, output.summary)
        except Exception as exc:
            msg = f"DigestService: video enrichment failed — {exc}"
            logger.error(msg, exc_info=True)
            errors.append(msg)

        logger.info(
            "DigestService: enriched %d articles, %d videos", art_count, vid_count
        )
        return art_count, vid_count, errors

    def _persist_enrichment(
        self, db, content_type: str, content_id: int, output: EnrichmentOutput,
    ) -> None:
        """Write ONE EnrichmentAgent call's result across the 3 M8 tables it touches."""
        ContentEnrichmentRepository(db).upsert(
            content_type=content_type,
            content_id=content_id,
            content_category=output.content_category,
            technical_depth=output.technical_depth,
            key_points=output.key_points,
            technical_details=output.technical_details,
            business_angle=output.business_angle,
            why_it_matters=output.why_it_matters,
            enrichment_version=self._enrichment_version,
        )
        ContentTopicRepository(db).replace_for_content(content_type, content_id, output.topics)
        ContentEntityRepository(db).replace_for_content(
            content_type, content_id, [(e.name, e.type) for e in output.entities],
        )

    def _reembed(self, db, content_type: str, content_id: int, summary: str) -> None:
        """
        Re-embed immediately after enrichment writes a new summary — without
        this, run_embedding_phase()'s exists_for() short-circuit would never
        re-embed this item, leaving clustering to work off a stale
        raw-content/title embedding computed before enrichment ever ran
        (M8 gap; Principle 9: keep derived artifacts current with the data
        that produced them).
        """
        text = (summary or "").strip()
        if not text:
            return
        try:
            vector = embed_text(text)
            EmbeddingRepository(db).upsert(content_type, content_id, vector)
        except Exception:
            logger.exception(
                "DigestService: failed to re-embed %s:%s after enrichment", content_type, content_id,
            )