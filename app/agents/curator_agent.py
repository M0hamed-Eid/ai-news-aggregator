# app/agents/curator_agent.py
#
# CuratorAgent: ranks a mixed list of Article + YoutubeVideo objects by
# relevance to a UserProfile.
#
# Changes from the uploaded version
# ----------------------------------
# 1. Moved to app/agents/ (correct project location).
# 2. Replaced openai.responses.parse() with openai.beta.chat.completions.parse()
#    — same fix as digest_agent.py; the uploaded API call doesn't exist.
# 3. Replaced the raw `dict`-based profile with the typed UserProfile dataclass
#    from app.config, eliminating KeyError risk and coupling agents to config.
# 4. Added a unified DigestItem datatype — a thin view-model that flattens
#    Article and YoutubeVideo into the same shape for the LLM prompt, following
#    the Adapter / ViewModel pattern.  No raw dicts leak into public methods.
# 5. rank_items() now accepts List[Article | YoutubeVideo] directly; callers
#    no longer need to pre-process database records.
# 6. rank_digests() retained (accepts pre-built DigestItem list) for callers
#    that have already done the conversion (e.g. run_pipeline.py).
# 7. build_digest_items() is a static helper that converts ORM records →
#    DigestItem; it is kept separate so it can be unit-tested without a DB.
# 8. Full type hints and docstrings added throughout.
# 9. Removed direct dotenv usage — handled globally in run_pipeline.py.


# Changes from previous version
# ----------------------------------
# 1. Switched from OpenAI to Groq (free tier).
# 2. Removed .beta.chat.completions.parse() — Groq doesn't support it.
#    JSON is requested explicitly in the prompt and parsed manually.
# 3. Uses llama-3.3-70b-versatile for better reasoning during ranking.
# 4. Added _strip_json_fences() helper (same pattern as digest_agent).
# 5. All DigestItem / RankedArticle / build_digest_items logic unchanged.

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Union

from groq import Groq
from pydantic import BaseModel, Field

from app.config import UserProfile
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# View-model: flat representation fed to the LLM
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DigestItem:
    """
    A flattened, LLM-ready view of either an Article or a YoutubeVideo.

    `digest_id` uniquely identifies the source record so callers can map
    the ranked results back to the original ORM object.
    Format: "<article_type>:<db_id>", e.g. "blog_openai:42" or "youtube:7".
    """
    digest_id: str        # "article_type:db_id"
    title: str
    summary: str          # AI-generated digest (may be empty string)
    article_type: str     # "blog_openai" | "blog_anthropic" | "youtube"
    db_id: int            # original PK for look-up


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class RankedArticle(BaseModel):
    digest_id: str = Field(description="The ID of the digest (article_type:article_id)")
    relevance_score: float = Field(
        description="Relevance score from 0.0 to 10.0", ge=0.0, le=10.0
    )
    rank: int = Field(description="Rank position (1 = most relevant)", ge=1)
    reasoning: str = Field(description="Brief explanation of why this article is ranked here")


# ---------------------------------------------------------------------------
# System-prompt builder
# ---------------------------------------------------------------------------

_BASE_CURATOR_PROMPT = """You are an expert AI news curator specialising in \
personalised content ranking for AI professionals.

Your role is to analyse and rank AI-related news articles, research papers, \
and video content based on a user's specific profile, interests, and background.

Ranking Criteria:
1. Relevance to user's stated interests and background
2. Technical depth and practical value
3. Novelty and significance of the content
4. Alignment with user's expertise level
5. Actionability and real-world applicability

Scoring Guidelines:
- 9.0-10.0: Highly relevant, directly aligns with user interests, significant value
- 7.0-8.9:  Very relevant, strong alignment with interests, good value
- 5.0-6.9:  Moderately relevant, some alignment, decent value
- 3.0-4.9:  Somewhat relevant, limited alignment, lower value
- 0.0-2.9:  Low relevance, minimal alignment, little value

Rank articles from most relevant (rank 1) to least relevant.
Ensure each article has a unique rank.

IMPORTANT: Respond ONLY with a valid JSON object. No markdown, no explanation.
Format:
{
  "articles": [
    {
      "digest_id": "...",
      "relevance_score": 8.5,
      "rank": 1,
      "reasoning": "..."
    }
  ]
}"""


def _build_system_prompt(profile: UserProfile) -> str:
    interests_text = "\n".join(f"  - {i}" for i in profile.interests)
    return (
        f"{_BASE_CURATOR_PROMPT}\n\n"
        f"User Profile:\n"
        f"  Name: {profile.name}\n"
        f"\nInterests:\n{interests_text}"
    )


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

class CuratorAgent:
    """
    Ranks content by relevance to a user profile.

    Usage
    -----
    from app.config import config
    agent = CuratorAgent(config.user)
    ranked = agent.rank_items(articles + videos)   # ORM objects
    """

    def __init__(self, user_profile: UserProfile) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])
        # llama-3.3-70b-versatile: stronger reasoning, better for ranking tasks
        self._model = "llama-3.3-70b-versatile"
        self._user_profile = user_profile
        self._system_prompt = _build_system_prompt(user_profile)

    # ------------------------------------------------------------------
    # Public — primary interface
    # ------------------------------------------------------------------

    def rank_items(
        self,
        items: List[Union[Article, YoutubeVideo]],
    ) -> List[RankedArticle]:
        """
        Rank a mixed list of Article and YoutubeVideo ORM objects.

        Returns a list of RankedArticle sorted by rank ascending
        (rank 1 = most relevant).
        """
        digests = self.build_digest_items(items)
        return self.rank_digests(digests)

    def rank_digests(self, digests: List[DigestItem]) -> List[RankedArticle]:
        """
        Rank a pre-built list of DigestItem objects.

        Use this when you have already converted ORM objects to DigestItem,
        e.g. when iterating in batches across the pipeline.
        """
        if not digests:
            return []

        digest_text = "\n\n".join(
            f"ID: {d.digest_id}\nTitle: {d.title}\nSummary: {d.summary}\nType: {d.article_type}"
            for d in digests
        )

        user_prompt = (
            f"Rank these {len(digests)} AI news digests based on the user profile:\n\n"
            f"{digest_text}\n\n"
            f"Provide a relevance score (0.0-10.0) and rank (1-{len(digests)}) "
            f"for each article, ordered from most to least relevant.\n\n"
            f"Respond ONLY with valid JSON matching this format:\n"
            f'{{"articles": [{{"digest_id": "...", "relevance_score": 8.5, '
            f'"rank": 1, "reasoning": "..."}}]}}'
        )

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(_strip_json_fences(raw))
            articles = [RankedArticle(**a) for a in data["articles"]]
            return sorted(articles, key=lambda a: a.rank)
        except json.JSONDecodeError as exc:
            logger.error("CuratorAgent: JSON parse error — %s", exc)
        except Exception:
            logger.exception("CuratorAgent: error ranking %d digests", len(digests))
        return []

    # ------------------------------------------------------------------
    # Static helper — ORM → DigestItem conversion
    # ------------------------------------------------------------------

    @staticmethod
    def build_digest_items(
        items: List[Union[Article, YoutubeVideo]],
    ) -> List[DigestItem]:
        """
        Convert a mixed list of ORM objects to DigestItem view-models.

        Articles and videos that have no summary yet are included with an
        empty summary string — the LLM will rely on the title alone for
        those, which is acceptable for ranking purposes.
        """
        result: List[DigestItem] = []
        for item in items:
            if isinstance(item, Article):
                result.append(
                    DigestItem(
                        digest_id=f"{item.source}:{item.id}",
                        title=item.title,
                        summary=item.summary or "",
                        article_type=item.source,
                        db_id=item.id,
                    )
                )
            elif isinstance(item, YoutubeVideo):
                result.append(
                    DigestItem(
                        digest_id=f"youtube:{item.id}",
                        title=item.title,
                        summary=item.summary or "",
                        article_type="youtube",
                        db_id=item.id,
                    )
                )
            else:
                logger.warning(
                    "CuratorAgent.build_digest_items: unknown type %s, skipping",
                    type(item).__name__,
                )
        return result