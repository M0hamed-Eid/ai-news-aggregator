# app/agents/email_agent.py
#
# EmailAgent: builds a complete EmailDigestResponse from a ranked list of
# Article / YoutubeVideo ORM objects.
#
# Changes from the uploaded version
# ----------------------------------
# 1. Moved to app/agents/ (correct project location).
# 2. Replaced openai.responses.parse() with openai.beta.chat.completions.parse().
# 3. Rewired to accept ORM objects (Article | YoutubeVideo) directly via a
#    new build_response() method, eliminating raw dicts and KeyError risk.
# 4. RankedArticleDetail is now populated from ORM attributes; it no longer
#    expects callers to construct dicts by hand.
# 5. EmailDigest (the "dict-payload" variant) is removed — it was a source of
#    confusion because it overlapped with EmailDigestResponse. EmailDigestResponse
#    is the single canonical output type.
# 6. to_markdown() produces a clean, deliverable-ready Markdown email body.
# 7. UserProfile pulled from app.config so the agent stays consistent with
#    the rest of the project.
# 8. Removed direct dotenv usage — handled globally in run_pipeline.py.
# 9. Full type hints throughout.

# Changes from previous version
# ----------------------------------
# 1. Switched from OpenAI to Groq (free tier).
# 2. Removed .beta.chat.completions.parse() — Groq doesn't support it.
#    JSON is requested explicitly in the prompt and parsed manually.
# 3. Added _strip_json_fences() helper (same pattern as other agents).
# 4. build_response() now accepts List[DigestItem] instead of ORM objects
#    directly — avoids DetachedInstanceError since DigestItems are plain
#    dataclasses that don't need an active SQLAlchemy session.
# 5. All EmailIntroduction / RankedArticleDetail / to_markdown() unchanged.

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from groq import Groq
from pydantic import BaseModel, Field

from app.agents.curator_agent import DigestItem, RankedArticle
from app.config import UserProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class EmailIntroduction(BaseModel):
    greeting: str = Field(description="Personalised greeting with user's name and date")
    introduction: str = Field(
        description="2-3 sentence overview of what's in the top 10 ranked articles"
    )


class RankedArticleDetail(BaseModel):
    """Enriched record combining LLM ranking with content data."""
    digest_id: str
    rank: int
    relevance_score: float
    title: str
    summary: str
    url: str
    article_type: str
    reasoning: Optional[str] = None
    image_url: Optional[str] = None
    reading_minutes: Optional[int] = 1


class EmailDigestResponse(BaseModel):
    introduction: EmailIntroduction
    articles: List[RankedArticleDetail]
    total_ranked: int
    top_n: int

    def to_markdown(self) -> str:
        """Render the digest as a Markdown string suitable for email delivery."""
        lines: List[str] = [
            self.introduction.greeting,
            "",
            self.introduction.introduction,
            "",
            "---",
            "",
        ]
        for article in self.articles:
            lines += [
                f"## {article.title}",
                "",
                article.summary,
                "",
                f"[Read more →]({article.url})",
                "",
                "---",
                "",
            ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_EMAIL_PROMPT = """You are an expert email writer specialising in creating \
engaging, personalised AI news digest emails.

Your role is to write a warm, professional introduction for a daily AI news \
digest email that:
- Greets the user by name.
- Includes the current date.
- Provides a brief, engaging overview of the top ranked articles.
- Highlights the most interesting or important themes.
- Sets expectations for the content ahead.

Keep it concise (2-3 sentences for the introduction), friendly, and professional.

IMPORTANT: Respond ONLY with a valid JSON object. No markdown, no explanation.
Format: {"greeting": "Hey [name]...", "introduction": "..."}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences that some models wrap around JSON output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class EmailAgent:
    """
    Builds a complete EmailDigestResponse from ranked content.

    Typical usage
    -------------
    from app.agents.curator_agent import CuratorAgent
    from app.agents.email_agent import EmailAgent

    digest_items = CuratorAgent.build_digest_items(articles + videos)
    ranked       = CuratorAgent(config.user).rank_digests(digest_items)
    response     = EmailAgent(config.user).build_response(
        ranked_scores=ranked,
        all_items=digest_items,
        limit=10,
    )
    print(response.to_markdown())
    """

    def __init__(self, user_profile: UserProfile) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])
        # 8b-instant is fast enough for the simple intro generation task
        self._model = "llama-3.1-8b-instant"
        self._user_profile = user_profile

    # ------------------------------------------------------------------
    # Primary public method
    # ------------------------------------------------------------------

    def build_response(
        self,
        *,
        ranked_scores: List[RankedArticle],
        all_items: List[DigestItem],
        limit: int = 10,
    ) -> EmailDigestResponse:
        """
        Build a full EmailDigestResponse.

        Parameters
        ----------
        ranked_scores : list of RankedArticle from CuratorAgent.rank_digests()
        all_items     : the DigestItem list (plain dataclasses — no ORM needed)
        limit         : how many articles to include in the digest (default 10)
        """
        # Build a lookup map: digest_id → DigestItem
        item_map: dict[str, DigestItem] = {d.digest_id: d for d in all_items}

        # Merge ranking metadata with digest content, preserving rank order
        details: List[RankedArticleDetail] = []
        for ranked in ranked_scores[:limit]:
            digest = item_map.get(ranked.digest_id)
            if digest is None:
                logger.warning(
                    "EmailAgent: no DigestItem found for digest_id=%r, skipping",
                    ranked.digest_id,
                )
                continue

            # Reconstruct a best-effort URL from the digest_id
            # Format is either "blog_openai:<id>", "blog_anthropic:<id>", "youtube:<id>"
            # The real URL lives in the DB but we stored enough info in DigestItem
            # to build a placeholder; callers that need the real URL should pass
            # a url_map (see note below).
            url = item_map.get(ranked.digest_id + "_url", digest.digest_id)

            details.append(
                RankedArticleDetail(
                    digest_id=ranked.digest_id,
                    rank=ranked.rank,
                    relevance_score=ranked.relevance_score,
                    title=digest.title,
                    summary=digest.summary,
                    url=getattr(digest, "url", ""),  # populated by build_response_from_orm
                    article_type=digest.article_type,
                    reasoning=ranked.reasoning,
                )
            )

        introduction = self._generate_introduction(details)

        return EmailDigestResponse(
            introduction=introduction,
            articles=details,
            total_ranked=len(ranked_scores),
            top_n=limit,
        )

    def build_response_with_urls(
        self,
        *,
        ranked_scores: List[RankedArticle],
        all_items: List[DigestItem],
        content_meta: dict[str, dict],
        limit: int = 10,
    ) -> EmailDigestResponse:
        """
        Same as build_response(), but injects real URLs coming from the database.
        """

        item_map: dict[str, DigestItem] = {
            d.digest_id: d for d in all_items
        }

        details: List[RankedArticleDetail] = []

        for ranked in ranked_scores[:limit]:
            digest = item_map.get(ranked.digest_id)

            if digest is None:
                logger.warning(
                    "EmailAgent: no DigestItem found for digest_id=%r, skipping",
                    ranked.digest_id,
                )
                continue
            content_info = content_meta.get(ranked.digest_id)
            if content_info is None:
                logger.warning(
                    "EmailAgent: no content meta found for digest_id=%r, skipping",
                    ranked.digest_id,
                )
                continue
            details.append(
                RankedArticleDetail(
                    digest_id=ranked.digest_id,
                    rank=ranked.rank,
                    relevance_score=ranked.relevance_score,
                    title=digest.title,
                    summary=digest.summary,
                    url=content_info["url"],
                    image_url=content_info["image_url"],
                    reading_minutes=content_info["reading_minutes"],
                    article_type=digest.article_type,
                    reasoning=ranked.reasoning,
                )
            )
        return EmailDigestResponse(
            introduction=self._generate_introduction(details),
            articles=details,
            total_ranked=len(ranked_scores),
            top_n=limit,
        )
    def build_response_from_orm(
        self,
        *,
        ranked_scores: List[RankedArticle],
        all_items,          # List[Article | YoutubeVideo] — typed loosely to avoid circular import
        limit: int = 10,
    ) -> EmailDigestResponse:
        """
        Build a full EmailDigestResponse directly from ORM objects.

        Use this variant when ORM objects are still attached to a session,
        e.g. when calling from inside a `with get_db_session()` block.

        Parameters
        ----------
        ranked_scores : list of RankedArticle from CuratorAgent
        all_items     : the original ORM objects (Articles + YoutubeVideos)
        limit         : how many articles to include in the digest (default 10)
        """
        from app.database.models.article import Article
        from app.database.models.youtube_video import YoutubeVideo

        # Build lookup: digest_id → ORM object
        item_map = {}
        for item in all_items:
            if isinstance(item, Article):
                key = f"{item.source}:{item.id}"
            else:
                key = f"youtube:{item.id}"
            item_map[key] = item

        details: List[RankedArticleDetail] = []
        for ranked in ranked_scores[:limit]:
            orm_item = item_map.get(ranked.digest_id)
            if orm_item is None:
                logger.warning(
                    "EmailAgent: no ORM record found for digest_id=%r, skipping",
                    ranked.digest_id,
                )
                continue
            details.append(
                RankedArticleDetail(
                    digest_id=ranked.digest_id,
                    rank=ranked.rank,
                    relevance_score=ranked.relevance_score,
                    title=orm_item.title,
                    summary=orm_item.summary or "",
                    url=meta.get("url", ""),
                    article_type=(
                        orm_item.source
                        if isinstance(orm_item, Article)
                        else "youtube"
                    ),
                    reasoning=ranked.reasoning,
                    image_url=meta.get("image_url", None),
                    reading_minutes=meta.get("reading_minutes", 1),
                )
            )

        introduction = self._generate_introduction(details)

        return EmailDigestResponse(
            introduction=introduction,
            articles=details,
            total_ranked=len(ranked_scores),
            top_n=limit,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_introduction(
        self,
        top_articles: List[RankedArticleDetail],
    ) -> EmailIntroduction:
        today = datetime.now().strftime("%B %d, %Y")
        name = self._user_profile.name

        fallback = EmailIntroduction(
            greeting=f"Hey {name}, here is your daily digest of AI news for {today}.",
            introduction="Here are the top AI news articles ranked by relevance to your interests.",
        )

        if not top_articles:
            return fallback

        article_lines = "\n".join(
            f"{idx + 1}. {a.title} (Score: {a.relevance_score:.1f}/10)"
            for idx, a in enumerate(top_articles)
        )
        user_prompt = (
            f"Create an email introduction for {name} for {today}.\n\n"
            f"Top ranked articles:\n{article_lines}\n\n"
            f"Generate a greeting and introduction that previews these articles.\n\n"
            f'Respond ONLY with JSON: {{"greeting": "Hey {name}...", "introduction": "..."}}'
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": _EMAIL_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(_strip_json_fences(raw))
            intro = EmailIntroduction(**data)

            # Enforce consistent greeting format
            if not intro.greeting.strip().startswith(f"Hey {name}"):
                intro = EmailIntroduction(
                    greeting=f"Hey {name}, here is your daily digest of AI news for {today}.",
                    introduction=intro.introduction,
                )
            return intro

        except json.JSONDecodeError as exc:
            logger.error("EmailAgent: JSON parse error — %s", exc)
        except Exception:
            logger.exception("EmailAgent: error generating introduction")
        return fallback