# app/agents/digest_agent.py
#
# DigestAgent: generates a concise title + 2-3 sentence summary for a single
# piece of content (article or YouTube video).
#
# Changes from the uploaded version
# ----------------------------------
# 1. Moved to app/agents/ (correct project location).
# 2. Replaced openai.responses.parse() with openai.beta.chat.completions.parse()
#    — the uploaded code used a non-existent / unstable API method.
#    The Structured-Outputs beta endpoint is the correct, stable way to get
#    Pydantic-validated responses from GPT models.
# 3. Added full type hints throughout.
# 4. Accepted both Article and YoutubeVideo ORM objects directly, so callers
#    don't have to manually extract fields before calling generate_digest().
# 5. Kept DigestOutput as a lean Pydantic model — no ORM coupling here so the
#    agent stays testable without a database.
# 6. Removed direct dotenv usage — the project already calls load_dotenv() in
#    run_pipeline.py before anything else is imported.

from __future__ import annotations

import logging
import os
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel

from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------

class DigestOutput(BaseModel):
    title: str
    summary: str


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an expert AI news analyst specialising in summarising \
technical articles, research papers, and video content about artificial intelligence.

Your role is to create concise, informative digests that help readers quickly \
understand the key points and significance of AI-related content.

Guidelines:
- Create a compelling title (5-10 words) that captures the essence of the content.
- Write a 2-3 sentence summary highlighting the main points and why they matter.
- Focus on actionable insights and implications.
- Use clear, accessible language while maintaining technical accuracy.
- Avoid marketing fluff — focus on substance."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DigestAgent:
    """Generates a title + summary digest for a single Article or YoutubeVideo."""

    def __init__(self) -> None:
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self._model = "gpt-4o-mini"

    # ------------------------------------------------------------------
    # Public interface — accepts ORM objects directly
    # ------------------------------------------------------------------

    def digest_article(self, article: Article) -> Optional[DigestOutput]:
        """Generate a digest for an Article ORM object."""
        content = article.content or ""
        return self._generate(
            article_type="blog article",
            title=article.title,
            content=content,
        )

    def digest_video(self, video: YoutubeVideo) -> Optional[DigestOutput]:
        """Generate a digest for a YoutubeVideo ORM object."""
        content = video.content or ""
        return self._generate(
            article_type="YouTube video transcript",
            title=video.title,
            content=content,
        )

    # ------------------------------------------------------------------
    # Lower-level helper — kept public so callers can pass raw strings
    # (useful for testing and for the pipeline's dry-run mode).
    # ------------------------------------------------------------------

    def generate_digest(
        self,
        title: str,
        content: str,
        article_type: str = "article",
    ) -> Optional[DigestOutput]:
        """Generate a digest from raw strings (title + content)."""
        return self._generate(article_type=article_type, title=title, content=content)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate(
        self,
        *,
        article_type: str,
        title: str,
        content: str,
    ) -> Optional[DigestOutput]:
        user_prompt = (
            f"Create a digest for this {article_type}:\n"
            f"Title: {title}\n"
            f"Content: {content[:8_000]}"
        )
        try:
            response = self._client.beta.chat.completions.parse(
                model=self._model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=DigestOutput,
            )
            return response.choices[0].message.parsed
        except Exception:
            logger.exception("DigestAgent: error generating digest for %r", title)
            return None