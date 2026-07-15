# app/agents/enrichment_agent.py
#
# EnrichmentAgent: ONE structured LLM call per item, replacing DigestAgent's
# narrow title+summary output (M8 — Content Intelligence Layer, Principle 4:
# "one enrichment call per item"). Produces everything downstream milestones
# need in a single pass: the same title/summary DigestAgent used to produce
# (persisted identically, so nothing downstream — the email template, card
# templates, CuratorAgent's ranking prompt — sees a behavior change there),
# PLUS content_category, technical_depth, structured summary fields,
# why_it_matters, topics (validated against the live taxonomy_topics
# vocabulary), and entities (typed company/model/person/technology mentions).
#
# No ORM/DB coupling for the LLM-calling part itself (stays testable without
# a database, same discipline as the old DigestAgent) — topic-vocabulary
# validation takes an explicit `allowed_topics: set[str]` constructor arg
# rather than querying the DB itself, so the caller (DigestService) controls
# when/how often that set is refreshed (once per pipeline run, not per item).

from __future__ import annotations

import json
import logging
import time
from typing import List, Literal, Optional, Set

from groq import RateLimitError as GroqRateLimitError
from openai import RateLimitError as OpenAIRateLimitError
from pydantic import BaseModel, Field

from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo
from app.llm.client_factory import get_llm_client_and_model

logger = logging.getLogger(__name__)

# Rate-limit-aware backoff — an explicit M8 Infrastructure requirement per
# docs/ROADMAP.md ("Groq TPM ceilings have bitten this project twice"), not
# optional polish. The enrichment call is exercised at MUCH higher sustained
# volume than the old DigestAgent ever was (full-corpus backfill), so this
# is where a rate-limit ceiling is actually likely to get hit for real.
MAX_RATE_LIMIT_RETRIES = 4
BASE_BACKOFF_SECONDS = 5.0

# Bumped whenever the prompt/schema changes meaningfully — persisted per-row
# in content_enrichment.enrichment_version so a future prompt change is
# identifiable in the data (distinguishing e.g. live-ingest rows from an
# older/backfill pass).
ENRICHMENT_VERSION = "v1"

CONTENT_CATEGORIES = [
    "research", "product-launch", "tutorial", "opinion",
    "funding", "announcement", "tooling", "other",
]
ENTITY_TYPES = ["company", "model", "person", "technology"]


# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------

class EntityMention(BaseModel):
    name: str
    type: Literal["company", "model", "person", "technology"]


class EnrichmentOutput(BaseModel):
    title: str
    summary: str
    content_category: Literal[
        "research", "product-launch", "tutorial", "opinion",
        "funding", "announcement", "tooling", "other",
    ]
    technical_depth: int = Field(ge=1, le=5)
    key_points: List[str]
    technical_details: str
    business_angle: str
    why_it_matters: str
    topics: List[str]
    entities: List[EntityMention]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """You are an expert AI news analyst who reads technical \
articles, research papers, and video content about artificial intelligence and \
produces a single structured analysis covering everything a downstream reader or \
recommender needs — not just a summary.

Guidelines:
- title: a compelling title (5-10 words) capturing the essence of the content.
- summary: a 2-3 sentence summary highlighting the main points and why they matter \
(same tone/length as a good news-digest summary — this is shown directly to readers).
- content_category: exactly ONE of: {categories}.
- technical_depth: an integer 1-5 (1 = accessible/non-technical, 5 = expert/research-level).
- key_points: 3-5 short bullet points, the core factual takeaways.
- technical_details: one paragraph on HOW it works technically (architecture, method, \
implementation) — empty string if the content has no real technical mechanics to describe.
- business_angle: one paragraph on the business/market/competitive implications — empty \
string if not applicable.
- why_it_matters: 1-2 sentences on why an AI-industry reader should care.
- topics: 1-3 topic slugs from this EXACT allowed list, choosing only ones that clearly \
apply (never invent a slug not in this list): {topics}.
- entities: every named company, AI model, person, or specific technology mentioned, \
each with its type (one of: company, model, person, technology). Omit generic terms.

IMPORTANT: Respond ONLY with a valid JSON object matching this exact shape, no markdown, \
no explanation:
{{"title": "...", "summary": "...", "content_category": "...", "technical_depth": 3, \
"key_points": ["...", "..."], "technical_details": "...", "business_angle": "...", \
"why_it_matters": "...", "topics": ["...", "..."], "entities": [{{"name": "...", "type": "..."}}]}}"""


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

class EnrichmentAgent:
    """
    Produces one EnrichmentOutput per Article/YoutubeVideo — the M8
    replacement for DigestAgent. `allowed_topics` is the live set of
    taxonomy_topics.slug values; any LLM-returned topic not in this set is
    dropped (logged), never invented into the database.
    """

    def __init__(self, allowed_topics: Set[str]) -> None:
        self._client, self._model = get_llm_client_and_model("simple")
        self._allowed_topics = allowed_topics
        self._system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            categories=", ".join(CONTENT_CATEGORIES),
            topics=", ".join(sorted(allowed_topics)),
        )

    # ------------------------------------------------------------------
    # Public interface — accepts ORM objects directly
    # ------------------------------------------------------------------

    def enrich_article(self, article: Article) -> Optional[EnrichmentOutput]:
        return self._generate(
            article_type="blog article", title=article.title, content=article.content or "",
        )

    def enrich_video(self, video: YoutubeVideo) -> Optional[EnrichmentOutput]:
        return self._generate(
            article_type="YouTube video transcript", title=video.title, content=video.content or "",
        )

    def generate(self, title: str, content: str, article_type: str = "article") -> Optional[EnrichmentOutput]:
        """Generate from raw strings — useful for tests / smoke checks."""
        return self._generate(article_type=article_type, title=title, content=content)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate(self, *, article_type: str, title: str, content: str) -> Optional[EnrichmentOutput]:
        user_prompt = (
            f"Analyze this {article_type}:\n"
            f"Title: {title}\n"
            f"Content: {content[:10_000]}\n\n"
            f"Respond ONLY with the JSON object described in the system prompt."
        )

        raw = self._call_with_backoff(user_prompt, title)
        if raw is None:
            return None

        try:
            data = json.loads(_strip_json_fences(raw))

            # Coerce enum-ish fields BEFORE constructing the strict Pydantic
            # model — a single bad enum value must not fail the whole call.
            # Confirmed live: the LLM occasionally confuses content_category
            # with a similarly-named taxonomy_topic slug (e.g. returns
            # "model-release"/"model-releases" — a real topic slug — instead
            # of a CONTENT_CATEGORIES value) for Hugging Face model-release
            # articles specifically.
            if data.get("content_category") not in CONTENT_CATEGORIES:
                logger.warning(
                    "EnrichmentAgent: invalid content_category %r for %r, falling back to 'other'",
                    data.get("content_category"), title,
                )
                data["content_category"] = "other"

            valid_entities = []
            for entity in data.get("entities", []) or []:
                if isinstance(entity, dict) and entity.get("name") and entity.get("type") in ENTITY_TYPES:
                    valid_entities.append(entity)
                else:
                    logger.warning("EnrichmentAgent: dropped invalid entity %r for %r", entity, title)
            data["entities"] = valid_entities

            try:
                depth = int(data.get("technical_depth", 3))
            except (TypeError, ValueError):
                depth = 3
            data["technical_depth"] = max(1, min(5, depth))

            output = EnrichmentOutput(**data)

            valid_topics = [t for t in output.topics if t in self._allowed_topics]
            dropped = set(output.topics) - set(valid_topics)
            if dropped:
                logger.warning("EnrichmentAgent: dropped unknown topic slug(s) %s for %r", dropped, title)
            output.topics = valid_topics

            return output
        except json.JSONDecodeError as exc:
            logger.error("EnrichmentAgent: JSON parse error for %r — %s", title, exc)
        except Exception:
            logger.exception("EnrichmentAgent: error enriching %r", title)
        return None

    def _call_with_backoff(self, user_prompt: str, title: str) -> Optional[str]:
        """
        Rate-limit-aware backoff (M8 Infrastructure requirement — "Groq TPM
        ceilings have bitten this project twice"). Retries ONLY on a real
        429/rate-limit response from either backend (Groq or Ollama's
        OpenAI-compatible client) with exponential backoff; any other
        exception (JSON parse, network, etc.) is the caller's problem, not
        retried here.
        """
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=0.5,
                    messages=[
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except (GroqRateLimitError, OpenAIRateLimitError):
                if attempt >= MAX_RATE_LIMIT_RETRIES:
                    logger.error(
                        "EnrichmentAgent: rate limited for %r — exhausted %d retries, giving up",
                        title, MAX_RATE_LIMIT_RETRIES,
                    )
                    return None
                backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "EnrichmentAgent: rate limited for %r — backing off %.1fs (attempt %d/%d)",
                    title, backoff, attempt + 1, MAX_RATE_LIMIT_RETRIES,
                )
                time.sleep(backoff)
            except Exception:
                logger.exception("EnrichmentAgent: error calling LLM for %r", title)
                return None
        return None
