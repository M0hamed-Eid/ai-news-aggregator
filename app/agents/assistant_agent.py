# app/agents/assistant_agent.py
#
# AssistantAgent (M14) — the RAG chat assistant's generation step. Same
# citation-trust philosophy as TrendNarrativeAgent (the highest hallucination-
# risk precedent in this codebase — "ground strictly in retrieved data; cite
# every claim"), adapted for free-form conversational text instead of a batch
# of discrete claims:
#
# - The model is given numbered sources and must cite them inline as [S1],
#   [S2], ... — never a raw id it could invent from memory.
# - Server-side, every cited marker is validated against the REAL handle map
#   this call was given. A marker that doesn't resolve (invented, or a typo)
#   is a citation TrendNarrativeAgent would drop the whole claim for — but
#   prose can't cleanly drop a "claim" without mangling the sentence, so here
#   the bracket marker itself is surgically stripped instead, and the answer
#   is flagged `grounded=False` if EVERY marker turned out to be invented (a
#   strong signal the model ignored the sources entirely).
# - If retrieval found nothing, the caller should skip this agent altogether
#   (see app/services/rag_service.py) rather than let the model answer from
#   pure training-data recall with zero sources to cite.
#
# build_system_prompt() is exposed standalone (not just used internally by
# AssistantAgent.generate()) because the streaming path (Phase D) needs a
# READY prompt string to hand to its own Groq client — Django can't import
# this whole module (app.* is off-limits there), but a Celery round-trip
# CAN return a plain string. See app/services/rag_service.py::
# build_retrieval_payload() and app/tasks/rag_tasks.py::rag_retrieve_task.
# The citation-stripping/suggestion-parsing logic below is small enough that
# apps/assistant/llm_client.py (Django) keeps its own documented copy rather
# than the whole agent — keep the two in sync if this logic changes.

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from groq import RateLimitError as GroqRateLimitError
from openai import RateLimitError as OpenAIRateLimitError

from app.llm.client_factory import get_llm_client_and_model

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 2  # shorter than the batch agents' 4 — this is an interactive, latency-sensitive call
BASE_BACKOFF_SECONDS = 2.0
CHAT_MAX_TOKENS = 700  # a few paragraphs — first max_tokens bound anywhere in this codebase (see cerebrum)

_CITATION_RE = re.compile(r"\[S(\d+)\]")
_SUGGESTIONS_RE = re.compile(r"\n?SUGGESTIONS:\s*(.+)\s*$", re.IGNORECASE | re.DOTALL)
MAX_SUGGESTIONS = 3

_STYLE_DIRECTIVES = {
    "beginner": "Explain in plain, beginner-friendly language. Avoid jargon; when you must use a technical term, define it in a few words.",
    "technical": "You may use precise technical terminology — assume the reader has an ML/software engineering background.",
    "concise": "Answer in one or two sentences, no more.",
}

_SYSTEM_PROMPT_TEMPLATE = """You are the AI assistant embedded in AI Compass, an AI-news platform. \
Answer the user's question using ONLY the numbered sources below — never your own outside knowledge, \
training data, or assumptions about content not shown here.

{scope_note}{style_directive}

Rules (follow all of these exactly):
- Cite every factual claim with a source marker like [S1] immediately after the claim.
- ONLY cite markers that are actually listed below. NEVER invent a marker, a source, or a fact.
- If the sources don't contain enough information to answer, say so plainly instead of guessing.
- Prefer direct quotes or timestamps when the user asks what someone said or when something happened.
- Keep your answer focused — under roughly 200 words unless the question genuinely requires more.
- After your answer, on its own final line, suggest up to {max_suggestions} short natural follow-up \
questions grounded in the same sources. Format exactly as one line:
SUGGESTIONS: question one? | question two? | question three?
Omit this line entirely if there's no good follow-up to suggest.

Numbered sources:
{sources_block}"""


def build_system_prompt(sources_block: str, scope_note: str = "", style: Optional[str] = None) -> str:
    """Standalone so the streaming path can get a ready prompt string via one
    Celery round-trip without importing this whole module into Django."""
    style_directive = f"\n{_STYLE_DIRECTIVES[style]}\n" if style in _STYLE_DIRECTIVES else ""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        scope_note=scope_note, style_directive=style_directive,
        sources_block=sources_block, max_suggestions=MAX_SUGGESTIONS,
    )


@dataclass
class Citation:
    marker: str
    content_type: str
    content_id: int
    chunk_index: int
    title: str
    url: str
    source: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None


@dataclass
class AssistantAnswer:
    text: str
    citations: List[Citation] = field(default_factory=list)
    grounded: bool = False
    suggestions: List[str] = field(default_factory=list)


def _extract_suggestions(text: str) -> "tuple[str, List[str]]":
    match = _SUGGESTIONS_RE.search(text)
    if not match:
        return text, []
    suggestions = [s.strip() for s in match.group(1).split("|") if s.strip()][:MAX_SUGGESTIONS]
    return text[: match.start()].rstrip(), suggestions


def _strip_and_resolve_citations(text: str, handle_to_citation: Dict[str, Citation]) -> AssistantAnswer:
    text, suggestions = _extract_suggestions(text)

    used_handles = sorted({int(m) for m in _CITATION_RE.findall(text)})

    def _sub(match: "re.Match") -> str:
        handle = f"S{match.group(1)}"
        return match.group(0) if handle in handle_to_citation else ""

    cleaned = _CITATION_RE.sub(_sub, text)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)  # tidy up spacing left by a stripped marker
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    resolved: List[Citation] = []
    for n in used_handles:
        handle = f"S{n}"
        citation = handle_to_citation.get(handle)
        if citation is None:
            logger.warning("AssistantAgent: dropped invented/unknown citation handle %r", handle)
            continue
        resolved.append(citation)

    return AssistantAnswer(text=cleaned, citations=resolved, grounded=len(resolved) > 0, suggestions=suggestions)


class AssistantAgent:

    def __init__(self) -> None:
        self._client, self.model = get_llm_client_and_model("chat")

    def generate(
        self,
        question: str,
        sources_block: str,
        handle_to_citation: Dict[str, Citation],
        scope_note: str = "",
        style: Optional[str] = None,
    ) -> Optional[AssistantAnswer]:
        """
        `sources_block`/`handle_to_citation` come from the same numbered-source
        assembly (see rag_service.py) — every [S#] the model could legitimately
        cite is a key in handle_to_citation; anything else it writes is an
        invented marker and gets stripped server-side. Returns None only on a
        total LLM-call failure (network/rate-limit exhaustion/unparseable);
        the caller should surface a "temporarily unavailable" response, not a
        hallucinated one.
        """
        system_prompt = build_system_prompt(sources_block, scope_note, style)
        raw = self._call_with_backoff(system_prompt, question)
        if raw is None:
            return None

        return _strip_and_resolve_citations(raw, handle_to_citation)

    def _call_with_backoff(self, system_prompt: str, question: str) -> Optional[str]:
        """Same rate-limit-aware backoff shape as TrendNarrativeAgent/EnrichmentAgent, tuned shorter for interactive latency."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    temperature=0.3,
                    max_tokens=CHAT_MAX_TOKENS,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                )
                return response.choices[0].message.content or ""
            except (GroqRateLimitError, OpenAIRateLimitError):
                if attempt >= MAX_RATE_LIMIT_RETRIES:
                    logger.error("AssistantAgent: rate limited — exhausted %d retries, giving up", MAX_RATE_LIMIT_RETRIES)
                    return None
                backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning("AssistantAgent: rate limited — backing off %.1fs (attempt %d/%d)", backoff, attempt + 1, MAX_RATE_LIMIT_RETRIES)
                time.sleep(backoff)
            except Exception:
                logger.exception("AssistantAgent: error calling LLM")
                return None
        return None
