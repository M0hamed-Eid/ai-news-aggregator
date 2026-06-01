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

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional, Union

from openai import OpenAI
from pydantic import BaseModel, Field

from app.agents.curator_agent import DigestItem, RankedArticle
from app.config import UserProfile
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo

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
    """Enriched record combining LLM ranking with ORM content."""
    digest_id: str
    rank: int
    relevance_score: float
    title: str
    summary: str
    url: str
    article_type: str
    reasoning: Optional[str] = None


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
- Provides a brief, engaging overview of the top 10 ranked articles.
- Highlights the most interesting or important themes.
- Sets expectations for the content ahead.

Keep it concise (2-3 sentences for the introduction), friendly, and professional."""


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

    ranked   = CuratorAgent(config.user).rank_items(articles + videos)
    response = EmailAgent(config.user).build_response(
        ranked_scores=ranked,
        all_items=articles + videos,
        limit=10,
    )
    print(response.to_markdown())
    """

    def __init__(self, user_profile: UserProfile) -> None:
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = "gpt-4o-mini"
        self._user_profile = user_profile

    # ------------------------------------------------------------------
    # Primary public method
    # ------------------------------------------------------------------

    def build_response(
        self,
        *,
        ranked_scores: List[RankedArticle],
        all_items: List[Union[Article, YoutubeVideo]],
        limit: int = 10,
    ) -> EmailDigestResponse:
        """
        Build a full EmailDigestResponse.

        Parameters
        ----------
        ranked_scores : list of RankedArticle from CuratorAgent.rank_items()
        all_items     : the original ORM objects (Articles + YoutubeVideos) so
                        we can look up URLs, summaries, etc.
        limit         : how many articles to include in the digest (default 10)
        """
        # Build a lookup map: digest_id → ORM object
        item_map: dict[str, Union[Article, YoutubeVideo]] = {}
        for item in all_items:
            if isinstance(item, Article):
                key = f"{item.source}:{item.id}"
            else:
                key = f"youtube:{item.id}"
            item_map[key] = item

        # Merge ranking metadata with ORM content, preserving rank order
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
                    url=orm_item.url,
                    article_type=(
                        orm_item.source
                        if isinstance(orm_item, Article)
                        else "youtube"
                    ),
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
            f"Generate a greeting and introduction that previews these articles."
        )

        try:
            response = self._client.beta.chat.completions.parse(
                model=self._model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": _EMAIL_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=EmailIntroduction,
            )
            intro = response.choices[0].message.parsed
            if intro is None:
                return fallback

            # Enforce consistent greeting format
            if not intro.greeting.strip().startswith(f"Hey {name}"):
                intro = EmailIntroduction(
                    greeting=f"Hey {name}, here is your daily digest of AI news for {today}.",
                    introduction=intro.introduction,
                )
            return intro
        except Exception:
            logger.exception("EmailAgent: error generating introduction")
            return fallback