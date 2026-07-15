# app/ranking/types.py
#
# Shared ranking view-model types — relocated out of app/agents/curator_agent.py
# (M9) before that module was deleted. These were never actually LLM-specific:
# UserProfile/DigestItem/RankedArticle are the generic contract EmailAgent,
# UserRankingRepository, and DigestService all build on, regardless of
# whether the ranking decision behind them comes from an LLM (the old
# CuratorAgent) or the deterministic two-stage ranker that replaced it
# (app/services/ranking_service.py) — moving them here avoids implying
# either.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Union

from pydantic import BaseModel, Field

from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo

# ---------------------------------------------------------------------------
# UserProfile — the ranking/personalization input every downstream consumer
# expects. Built fresh per recipient at ranking/digest time (app/services/
# recipients.py), never a single shared global (see recipients.py's own
# docstring for the multi-user-migration history behind that).
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    """Represents the person a ranking/digest is being built for."""
    name: str = "Mohammed"
    email: str = ""

    interests: List[str] = field(default_factory=lambda: [
        "large language models",
        "AI agents",
        "open source models",
        "NLP",
        "machine learning research",
        "RAG and vector databases",
    ])

    expertise_level: str = "advanced"  # beginner | intermediate | advanced

    preferences: Dict[str, str] = field(default_factory=lambda: {
        "content_depth": "technical",       # technical | overview
        "preferred_sources": "all",         # all | youtube | blogs
        "max_video_length": "any",          # any | short | medium
    })


# ---------------------------------------------------------------------------
# View-model: flat representation of one content item
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DigestItem:
    """
    A flattened view of either an Article or a YoutubeVideo, shared across
    ranking and email-building so neither has to touch ORM objects directly.

    `digest_id` uniquely identifies the source record so callers can map
    ranked results back to the original ORM object.
    Format: "<article_type>:<db_id>", e.g. "blog_openai:42" or "youtube:7".
    """
    digest_id: str        # "article_type:db_id"
    title: str
    summary: str          # AI-generated summary (may be empty string)
    article_type: str     # "blog_openai" | "blog_anthropic" | "youtube" | ...
    db_id: int             # original PK for look-up


# ---------------------------------------------------------------------------
# Ranking output
# ---------------------------------------------------------------------------

class RankedArticle(BaseModel):
    digest_id: str = Field(description="The ID of the digest (article_type:article_id)")
    relevance_score: float = Field(description="Relevance score from 0.0 to 10.0", ge=0.0, le=10.0)
    rank: int = Field(description="Rank position (1 = most relevant)", ge=1)
    reasoning: str = Field(default="", description="Human-readable explanation of why this item is ranked here")
    features: dict = Field(
        default_factory=dict,
        description="Exact scoring feature snapshot that produced this rank (Principle 7) — persisted to user_rankings.features",
    )


# ---------------------------------------------------------------------------
# ORM -> DigestItem conversion
# ---------------------------------------------------------------------------

def build_digest_items(items: List[Union[Article, YoutubeVideo]]) -> List[DigestItem]:
    """
    Convert a mixed list of ORM objects to DigestItem view-models.

    Articles and videos that have no summary yet are included with an empty
    summary string — callers rely on other fields (topics/entities/scores)
    for those, which is acceptable since M8's enrichment covers the corpus.
    """
    import logging

    logger = logging.getLogger(__name__)

    result: List[DigestItem] = []
    for item in items:
        if isinstance(item, Article):
            result.append(DigestItem(
                digest_id=f"{item.source}:{item.id}",
                title=item.title,
                summary=item.summary or "",
                article_type=item.source,
                db_id=item.id,
            ))
        elif isinstance(item, YoutubeVideo):
            result.append(DigestItem(
                digest_id=f"youtube:{item.id}",
                title=item.title,
                summary=item.summary or "",
                article_type="youtube",
                db_id=item.id,
            ))
        else:
            logger.warning("build_digest_items: unknown type %s, skipping", type(item).__name__)
    return result
