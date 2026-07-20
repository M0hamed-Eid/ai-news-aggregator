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
import re

from django.conf import settings
from groq import Groq

logger = logging.getLogger(__name__)

MODEL = "llama-3.3-70b-versatile"  # same model as app/llm/client_factory.py's "chat"/"reasoning" tier
MAX_TOKENS = 700  # same as app/agents/assistant_agent.py's CHAT_MAX_TOKENS — keep in sync

_CITATION_RE = re.compile(r"\[S(\d+)\]")
_SUGGESTIONS_RE = re.compile(r"\n?SUGGESTIONS:\s*(.+)\s*$", re.IGNORECASE | re.DOTALL)
MAX_SUGGESTIONS = 3


def is_configured() -> bool:
    return bool(getattr(settings, "GROQ_API_KEY", ""))


def stream_completion(system_prompt: str, question: str):
    """Yields raw text deltas as Groq produces them. Caller accumulates the
    full text and runs extract_suggestions()/resolve_citations() once the
    stream ends — never mid-stream, since a marker or the SUGGESTIONS
    trailer can straddle a chunk boundary."""
    client = Groq(api_key=settings.GROQ_API_KEY)
    stream = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        max_tokens=MAX_TOKENS,
        stream=True,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
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
