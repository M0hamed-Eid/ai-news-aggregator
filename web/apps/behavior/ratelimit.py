"""
Minimal first-party + rate-limit helpers for the event ingestion endpoint —
this is the first JSON/AJAX surface in this codebase (confirmed: no existing
django-ratelimit/DRF/CSRF-exempt precedent anywhere), so there's no
convention to match; kept intentionally small, no new dependency beyond the
`redis` package already added for the CACHES backend.
"""
from urllib.parse import urlparse

from django.core.cache import cache


def is_first_party(request) -> bool:
    """
    navigator.sendBeacon sends an opaque Blob body, so it can't populate
    request.POST or carry a custom header — a CSRF token can't travel with
    it regardless of what we do. "First-party only" is enforced via
    Origin (falling back to Referer) host-matching instead. Django's
    SECURE_REFERRER_POLICY defaults to "same-origin", so a legitimate
    same-origin beacon call reliably sends one of these; a cross-site call
    sends neither, or a mismatched host.
    """
    host = request.get_host()
    origin = request.headers.get("Origin")
    if origin:
        return urlparse(origin).netloc == host
    referer = request.headers.get("Referer")
    if referer:
        return urlparse(referer).netloc == host
    return False


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window counter. Returns True if the request is ALLOWED. A small
    race under concurrent requests (two requests both read None and both
    write 1) is an accepted tradeoff for a soft per-minute analytics limiter
    — not worth reaching for atomic-only primitives for this use case.
    """
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, timeout=window_seconds)
        return True
    if count >= limit:
        return False
    cache.incr(key)
    return True
