"""
Direct Groq client for the STREAMING chat path only (M14 Phase D) — the one
disclosed, deliberate exception to "web/ is ML/LLM-free" (see
app/services/rag_service.py's module docstring and the architecture RFC's
decision log). Retrieval still crosses to the pipeline via Celery
(rag_client.retrieve -> rag_retrieve_task) exactly as the non-streaming path
does; only token-by-token GENERATION happens here, because Celery's
request/response boundary can't stream and the non-streaming path
(AssistantMessageView) already covers the no-JS / Render-fallback case.

Citation-marker/suggestion parsing below is a SMALL, deliberate duplicate of
app/agents/assistant_agent.py's _strip_and_resolve_citations/
_extract_suggestions — the prompt TEMPLATE itself is never duplicated (it's
built pipeline-side in build_retrieval_payload() and handed over as a ready
string); only this mechanical regex post-processing is copied. Keep the two
in sync if either changes.
"""
import logging
import os
import re

from django.conf import settings
from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    Groq,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# [2026-08-22] Groq retired the entire llama-3.x chat family (both this and
# app/llm/client_factory.py's "chat"/"reasoning" tier used
# llama-3.3-70b-versatile, now a 404 model_not_found) -- see that file's own
# note on the same date. openai/gpt-oss-120b is Groq's current replacement,
# same model both places use, kept in sync manually since web/ and app/ are
# separate deploy units with no shared import path.
MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 700  # same as app/agents/assistant_agent.py's CHAT_MAX_TOKENS — keep in sync

_CITATION_RE = re.compile(r"\[S(\d+)\]")
_SUGGESTIONS_RE = re.compile(r"\n?SUGGESTIONS:\s*(.+)\s*$", re.IGNORECASE | re.DOTALL)
MAX_SUGGESTIONS = 3

# Errors where a DIFFERENT key is worth trying — same set as
# app/llm/groq_key_manager.py's _RETRYABLE_PER_KEY, deliberately
# re-declared rather than imported: web/ and the pipeline (app/) are
# separate deploy units with separate virtualenvs/dependency installs, no
# shared import path between them (same reasoning as this file's own
# existing citation/suggestion-parsing duplication, see module docstring
# above — small deliberate duplicate, keep the two lists in sync).
_RETRYABLE_PER_KEY = (
    RateLimitError, APIConnectionError, APITimeoutError,
    InternalServerError, AuthenticationError, PermissionDeniedError,
)


def _load_groq_keys() -> list:
    """GROQ_API_KEY_1, GROQ_API_KEY_2, ... via Django settings (falling back
    to os.environ so a key set only at the process level still works),
    stopping at the first gap; falls back to the single settings.GROQ_API_KEY
    if no numbered keys exist. Never logs a key value."""
    keys = []
    i = 1
    while True:
        key = getattr(settings, f"GROQ_API_KEY_{i}", "") or os.environ.get(f"GROQ_API_KEY_{i}", "")
        if not key:
            break
        keys.append(key)
        i += 1
    if not keys and getattr(settings, "GROQ_API_KEY", ""):
        keys.append(settings.GROQ_API_KEY)
    return keys


def is_configured() -> bool:
    return bool(_load_groq_keys())


def stream_completion(system_prompt: str, question: str):
    """Yields raw text deltas as Groq produces them. Caller accumulates the
    full text and runs extract_suggestions()/resolve_citations() once the
    stream ends — never mid-stream, since a marker or the SUGGESTIONS
    trailer can straddle a chunk boundary.

    Multi-key failover applies ONLY to opening the stream (the `.create()`
    call itself) — once Groq has started sending real chunks to a caller,
    switching keys mid-stream would mean silently re-sending/duplicating
    output, which is worse than just failing. A failure once tokens have
    already started is caught one level up by AssistantStreamView's own
    try/except, which sends a clean SSE error frame instead of a broken
    connection — that existing behavior is unchanged here."""
    keys = _load_groq_keys()
    if not keys:
        raise RuntimeError("stream_completion called with no Groq key configured — check is_configured() first")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    last_error = None
    stream = None
    for idx, key in enumerate(keys, start=1):
        try:
            client = Groq(api_key=key)
            stream = client.chat.completions.create(
                model=MODEL, temperature=0.3, max_tokens=MAX_TOKENS, stream=True, messages=messages,
                # gpt-oss is a REASONING model -- it spends completion tokens
                # on an internal `reasoning` field before any visible
                # `content`. Without capping effort, MAX_TOKENS=700 can be
                # consumed entirely by reasoning, streaming zero visible
                # chunks (confirmed live: default effort produced
                # content="" with finish_reason="length" on a 10-token
                # budget). "low" leaves the budget for an actual answer.
                reasoning_effort="low",
            )
            break
        except _RETRYABLE_PER_KEY as exc:
            logger.warning(
                "assistant streaming: key %d/%d failed to open (%s) — trying next key",
                idx, len(keys), type(exc).__name__,
            )
            last_error = exc
            continue
    if stream is None:
        raise last_error

    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


def extract_suggestions(text: str):
    match = _SUGGESTIONS_RE.search(text)
    if not match:
        return text, []
    suggestions = [s.strip() for s in match.group(1).split("|") if s.strip()][:MAX_SUGGESTIONS]
    return text[: match.start()].rstrip(), suggestions


def resolve_citations(text: str, handle_to_citation: dict):
    """handle_to_citation: {"S1": {...citation dict...}, ...} — the exact
    shape rag_retrieve_task returns (already JSON-safe dicts, no dataclass
    import needed here)."""
    used_handles = sorted({int(m) for m in _CITATION_RE.findall(text)})

    def _sub(match):
        handle = "S" + match.group(1)
        return match.group(0) if handle in handle_to_citation else ""

    cleaned = _CITATION_RE.sub(_sub, text)
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    resolved = []
    for n in used_handles:
        handle = "S" + str(n)
        citation = handle_to_citation.get(handle)
        if citation is None:
            logger.warning("assistant streaming: dropped invented/unknown citation handle %r", handle)
            continue
        resolved.append(citation)

    return cleaned, resolved
