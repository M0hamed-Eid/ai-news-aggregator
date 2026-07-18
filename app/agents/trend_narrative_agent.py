# app/agents/trend_narrative_agent.py
#
# TrendNarrativeAgent (M11, Pro) — the weekly grounded, cited trend
# narrative. The single highest hallucination-risk feature on the whole
# roadmap ("Insight hallucination is a trust risk, and trust is the
# product... ground strictly in retrieved data; cite every claim; never
# let the narrative invent connections... ship last within the milestone").
#
# Reuses EnrichmentAgent's exact validation shape (parse JSON -> coerce/drop
# malformed entries on the raw dict -> construct a strict Pydantic model ->
# post-hoc filter against a live allowed-set), but the post-hoc filter here
# does something stronger than EnrichmentAgent's topic-slug check: it
# resolves citation HANDLES ([S1], [S2], ...), never raw integer ids, so the
# LLM never gets the chance to reproduce/fabricate a real-looking content_id
# from memory — an invented handle simply fails to resolve server-side and
# is dropped. It also checks each claim's (trend_dimension, trend_key)
# against the ACTUAL trending set this call was given, so the model can't
# write about a "trend" it invented. Any claim with zero surviving real
# citations after resolution is dropped ENTIRELY — a claim with no real
# citations is by definition unsupported (the roadmap's own "cite every
# claim" wording, made mechanically checkable rather than trusted).
#
# Auto-publishes after this validation (no draft/review gate exists
# anywhere in this codebase, and none is introduced here — user-confirmed
# design decision, see docs/ROADMAP.md M11 and the M11 plan) — the raw,
# pre-filter LLM output is kept alongside (trend_reports.raw_narrative,
# never rendered to users) specifically so a human spot-check has the
# "what did it originally say vs. what survived filtering" diff available.

from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional, Tuple

from groq import RateLimitError as GroqRateLimitError
from openai import RateLimitError as OpenAIRateLimitError
from pydantic import BaseModel

from app.llm.client_factory import get_llm_client_and_model

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 4
BASE_BACKOFF_SECONDS = 5.0
NARRATIVE_VERSION = "v1"


class NarrativeClaim(BaseModel):
    headline: str
    body: str
    trend_dimension: str
    trend_key: str
    citation_handles: List[str]


class TrendNarrativeOutput(BaseModel):
    claims: List[NarrativeClaim]


_SYSTEM_PROMPT_TEMPLATE = """You are an AI-industry analyst writing a short, strictly \
factual weekly briefing about what's trending in AI right now.

You must ground EVERY claim ONLY in the numbered source items given below — never in \
outside knowledge, training data, or assumptions.

Rules (violating any of these makes your output unusable and it will be discarded):
- Every claim you write MUST cite at least one source handle (e.g. [S3]) from the list below.
- ONLY cite handles that are actually given to you below. NEVER invent a handle, a source, or a fact.
- NEVER state a connection, cause, or implication that isn't directly supported by a cited source's own title/summary.
- If you cannot support a claim with a real cited source, do not make that claim at all.
- Write exactly one claim-unit for each trending item listed below, in the same order.

Trending items to write about:
{trend_list}

Numbered sources (cite ONLY these, by handle — never a number/id not shown here):
{sources_block}

Respond ONLY with a valid JSON object matching this exact shape, no markdown, no explanation:
{{"claims": [{{"headline": "...", "body": "...", "trend_dimension": "topic", \
"trend_key": "...", "citation_handles": ["S1", "S3"]}}]}}"""


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class TrendNarrativeAgent:

    def __init__(self) -> None:
        self._client, self.model = get_llm_client_and_model("simple")

    def generate(
        self,
        trending: List[dict],
        handle_to_ref: Dict[str, Tuple[str, int]],
        sources_prompt_block: str,
    ) -> Tuple[Optional[List[dict]], Optional[List[dict]]]:
        """
        `trending`: this week's top trends, as [{"dimension", "key", "display_name"}, ...] —
            also the allow-list a claim's (trend_dimension, trend_key) is checked against.
        `handle_to_ref`: {"S1": ("article", 123), ...} — the ONLY handles that can resolve
            to a real citation; anything else the LLM cites is dropped.
        `sources_prompt_block`: pre-formatted numbered-source text embedded in the prompt.

        Returns (filtered_claims, raw_claims) as plain dicts ready for
        trend_reports.narrative / .raw_narrative — filtered is what's shown
        to users (server-validated citations only, ungrounded claims
        dropped), raw is the untouched LLM output for spot-check auditing
        (never rendered to users). Returns (None, None) on total failure
        (LLM call failed / unparseable response) — the caller should skip
        publishing this week's report rather than show a broken one.
        """
        trend_list = "\n".join(f"- {t['display_name']} ({t['dimension']}: {t['key']})" for t in trending)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(trend_list=trend_list, sources_block=sources_prompt_block)

        raw = self._call_with_backoff(system_prompt)
        if raw is None:
            return None, None

        try:
            data = json.loads(_strip_json_fences(raw))
        except json.JSONDecodeError as exc:
            logger.error("TrendNarrativeAgent: JSON parse error — %s", exc)
            return None, None

        raw_claim_dicts = data.get("claims", []) or []

        # Coerce/drop malformed claim dicts BEFORE constructing the strict
        # Pydantic model — one bad claim must not fail the whole batch.
        valid_shape_claims = []
        for c in raw_claim_dicts:
            if not isinstance(c, dict):
                continue
            if not all(isinstance(c.get(k), str) for k in ("headline", "body", "trend_dimension", "trend_key")):
                logger.warning("TrendNarrativeAgent: dropped malformed claim (missing/non-string fields): %r", c)
                continue
            handles = c.get("citation_handles")
            if not isinstance(handles, list) or not all(isinstance(h, str) for h in handles):
                logger.warning("TrendNarrativeAgent: dropped claim with malformed citation_handles: %r", c)
                continue
            valid_shape_claims.append(c)

        try:
            output = TrendNarrativeOutput(claims=valid_shape_claims)
        except Exception:
            logger.exception("TrendNarrativeAgent: failed constructing TrendNarrativeOutput")
            return None, raw_claim_dicts

        # Mechanical grounding filter — the actual hallucination guard:
        allowed_trends = {(t["dimension"], t["key"]) for t in trending}
        filtered: List[dict] = []
        for claim in output.claims:
            if (claim.trend_dimension, claim.trend_key) not in allowed_trends:
                logger.warning(
                    "TrendNarrativeAgent: dropped claim about an untrended (%s, %s) — not in this week's real trending set",
                    claim.trend_dimension, claim.trend_key,
                )
                continue

            resolved_citations = []
            for handle in claim.citation_handles:
                ref = handle_to_ref.get(handle)
                if ref is None:
                    logger.warning("TrendNarrativeAgent: dropped invented/unknown citation handle %r", handle)
                    continue
                content_type, content_id = ref
                resolved_citations.append({"content_type": content_type, "content_id": content_id})

            if not resolved_citations:
                logger.warning(
                    "TrendNarrativeAgent: dropped claim %r — zero real citations survived resolution",
                    claim.headline,
                )
                continue

            filtered.append({
                "headline": claim.headline,
                "body": claim.body,
                "trend_dimension": claim.trend_dimension,
                "trend_key": claim.trend_key,
                "citations": resolved_citations,
            })

        return filtered, raw_claim_dicts

    def _call_with_backoff(self, system_prompt: str) -> Optional[str]:
        """Same rate-limit-aware backoff as EnrichmentAgent — see that module for the M8 Infrastructure rationale."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    temperature=0.4,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Write the weekly briefing now, following every rule exactly."},
                    ],
                )
                return response.choices[0].message.content or ""
            except (GroqRateLimitError, OpenAIRateLimitError):
                if attempt >= MAX_RATE_LIMIT_RETRIES:
                    logger.error("TrendNarrativeAgent: rate limited — exhausted %d retries, giving up", MAX_RATE_LIMIT_RETRIES)
                    return None
                backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning("TrendNarrativeAgent: rate limited — backing off %.1fs (attempt %d/%d)", backoff, attempt + 1, MAX_RATE_LIMIT_RETRIES)
                time.sleep(backoff)
            except Exception:
                logger.exception("TrendNarrativeAgent: error calling LLM")
                return None
        return None
