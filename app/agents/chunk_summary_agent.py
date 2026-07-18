# app/agents/chunk_summary_agent.py
#
# ChunkSummaryAgent: ONE structured LLM call per ~10-minute chunk of a long
# video's transcript (M12 — Deep Media "map" step; the "reduce" step reuses
# the EXISTING EnrichmentAgent.generate(), fed these chunk summaries
# concatenated — see run_pipeline.py's run_deep_video_phase).
#
# Deliberately its own file/schema rather than sharing EnrichmentAgent's —
# chunk-level output is much narrower (chapter_title + summary only; no
# content_category/topics/entities/etc, which only make sense at whole-item
# granularity). Copies EnrichmentAgent's rate-limit backoff verbatim rather
# than factoring out a shared helper — matches this codebase's established
# convention (TrendNarrativeAgent made the same choice for M11).

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from groq import RateLimitError as GroqRateLimitError
from openai import RateLimitError as OpenAIRateLimitError
from pydantic import BaseModel

from app.llm.client_factory import get_llm_client_and_model

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 4
BASE_BACKOFF_SECONDS = 5.0

# Persisted per-row in content_chunks.summary_version (same convention as
# EnrichmentAgent.ENRICHMENT_VERSION / content_enrichment.enrichment_version).
CHUNK_SUMMARY_VERSION = "v1"

_SYSTEM_PROMPT = """You are an expert AI news analyst summarizing ONE segment of a \
longer video transcript into a chapter. You will be given a slice of transcript text \
(roughly 10 minutes of spoken content) and must produce:
- chapter_title: a short (3-8 word) title capturing what this segment is about.
- summary: a 2-4 sentence summary of what's discussed in this segment specifically.

IMPORTANT: Respond ONLY with a valid JSON object matching this exact shape, no markdown, \
no explanation:
{"chapter_title": "...", "summary": "..."}"""


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


class ChunkSummary(BaseModel):
    chapter_title: str
    summary: str


class ChunkSummaryAgent:
    """Produces one ChunkSummary per transcript chunk (chunk-boundary helper in run_pipeline.py)."""

    def __init__(self) -> None:
        self._client, self._model = get_llm_client_and_model("simple")

    def generate(self, video_title: str, chunk_text: str) -> Optional[ChunkSummary]:
        user_prompt = (
            f"Video title: {video_title}\n"
            f"Transcript segment:\n{chunk_text[:10_000]}\n\n"
            f"Respond ONLY with the JSON object described in the system prompt."
        )
        raw = self._call_with_backoff(user_prompt, video_title)
        if raw is None:
            return None
        try:
            data = json.loads(_strip_json_fences(raw))
            return ChunkSummary(**data)
        except json.JSONDecodeError as exc:
            logger.error("ChunkSummaryAgent: JSON parse error for %r — %s", video_title, exc)
        except Exception:
            logger.exception("ChunkSummaryAgent: error summarizing chunk for %r", video_title)
        return None

    def _call_with_backoff(self, user_prompt: str, title: str) -> Optional[str]:
        """Rate-limit-aware backoff — verbatim copy of EnrichmentAgent's, see that file's own comment for why."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    temperature=0.3,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except (GroqRateLimitError, OpenAIRateLimitError):
                if attempt >= MAX_RATE_LIMIT_RETRIES:
                    logger.error(
                        "ChunkSummaryAgent: rate limited for %r — exhausted %d retries, giving up",
                        title, MAX_RATE_LIMIT_RETRIES,
                    )
                    return None
                backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "ChunkSummaryAgent: rate limited for %r — backing off %.1fs (attempt %d/%d)",
                    title, backoff, attempt + 1, MAX_RATE_LIMIT_RETRIES,
                )
                time.sleep(backoff)
            except Exception:
                logger.exception("ChunkSummaryAgent: error calling LLM for %r", title)
                return None
        return None
