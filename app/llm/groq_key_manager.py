# app/llm/groq_key_manager.py
#
# Multi-key Groq failover (production-readiness audit, M16). Drop-in
# replacement for a raw `Groq(api_key=...)` client — exposes the exact same
# `.chat.completions.create(...)` call shape every existing agent already
# uses (EnrichmentAgent, TrendNarrativeAgent, EmailAgent, ChunkSummaryAgent,
# AssistantAgent, RAG's condense_query — all 6 call sites that go through
# get_llm_client_and_model()), so NOT ONE of them needed to change to gain
# failover.
#
# Design: tries each configured key in order with NO delay between keys — a
# fresh key isn't rate-limited just because another one is, so waiting
# before trying it would only slow down a fast, cheap fallback. Only once
# EVERY key has failed on this pass does it re-raise the last real
# exception (never a synthetic one) — every existing agent's own
# _call_with_backoff already catches GroqRateLimitError/OpenAIRateLimitError
# and retries the WHOLE call (i.e. the whole key cycle) with exponential
# backoff, so re-raising the genuine exception type means that existing
# outer retry loop keeps working completely unchanged. Total worst case is
# bounded: N_keys attempts per outer-retry pass, times the agent's own
# existing MAX_RATE_LIMIT_RETRIES+1 passes — no per-key backoff stacking on
# top of that, so adding keys does not multiply the worst-case wall-clock
# delay the way naively nesting two retry loops would.
#
# Never logs a key value — only its position ("key 2/3").

import logging
import os
from typing import List

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

# Errors where trying a DIFFERENT key is a reasonable, likely-to-help
# response: the request itself may be fine, just this one key's quota/
# validity/route is the problem. Deliberately excludes BadRequestError/
# UnprocessableEntityError/NotFoundError — a malformed request fails
# identically on every key, so retrying it N times would just waste time.
_RETRYABLE_PER_KEY = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    AuthenticationError,
    PermissionDeniedError,
)


def load_groq_keys() -> List[str]:
    """GROQ_API_KEY_1, GROQ_API_KEY_2, ... read in order, stopping at the
    first gap. Falls back to the plain GROQ_API_KEY (no suffix) if no
    numbered keys exist at all, so an existing single-key deployment needs
    zero configuration changes to keep working exactly as before."""
    keys = []
    i = 1
    while True:
        key = os.environ.get(f"GROQ_API_KEY_{i}")
        if not key:
            break
        keys.append(key)
        i += 1
    if not keys:
        fallback = os.environ.get("GROQ_API_KEY")
        if fallback:
            keys.append(fallback)
    return keys


class _CompletionsProxy:
    def __init__(self, clients: list):
        self._clients = clients

    def create(self, **kwargs):
        last_error = None
        for idx, client in enumerate(self._clients, start=1):
            try:
                return client.chat.completions.create(**kwargs)
            except _RETRYABLE_PER_KEY as exc:
                logger.warning(
                    "GroqKeyManager: key %d/%d failed (%s) — trying next key",
                    idx, len(self._clients), type(exc).__name__,
                )
                last_error = exc
                continue
        # Every key failed on this pass. Re-raise the LAST real SDK
        # exception (never a synthetic stand-in) so callers' existing
        # `except (GroqRateLimitError, ...)` handling sees a genuine,
        # correctly-typed error and keeps working unmodified.
        raise last_error


class _ChatProxy:
    def __init__(self, clients: list):
        self.completions = _CompletionsProxy(clients)


class GroqKeyManager:
    """`client_factory.py` returns this instead of a raw `Groq(...)` client
    whenever more than one key is configured. `manager.chat.completions.
    create(**kwargs)` behaves exactly like the real SDK call, just with
    automatic key failover underneath."""

    def __init__(self, keys: List[str]):
        if not keys:
            raise ValueError("GroqKeyManager: no GROQ_API_KEY_* or GROQ_API_KEY configured")
        self._clients = [Groq(api_key=k) for k in keys]
        self.chat = _ChatProxy(self._clients)

    @property
    def key_count(self) -> int:
        return len(self._clients)
