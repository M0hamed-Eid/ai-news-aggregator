"""
Minimal first-party + rate-limit helpers for the event ingestion endpoint —
this is the first JSON/AJAX surface in this codebase (confirmed: no existing
django-ratelimit/DRF/CSRF-exempt precedent anywhere), so there's no
convention to match; kept intentionally small, no new dependency beyond the
`redis` package already added for the CACHES backend.
"""
from urllib.parse import urlparse

from django.conf import settings
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

    Also accepts any origin listed in CSRF_TRUSTED_ORIGINS — the SAME
    setting this project already uses for "the SPA isn't literally
    same-origin as Django but IS first-party" (settings/dev.py hardcodes
    "http://localhost:3000" for exactly this reason: local dev runs Next.js
    on a different port than Django's runserver, proxied via next.config.ts's
    rewrites(), so a real browser-originated request here carries
    Origin: http://localhost:3000 while request.get_host() reports Django's
    own 127.0.0.1:8000 — a real mismatch confirmed live once the SPA
    started calling this endpoint (M15 Phase 5), never triggered before
    since beacon.js's only prior caller was Django's own directly-served
    pages). In production Caddy unifies both services under one domain
    (see settings/prod.py's own comment), so CSRF_TRUSTED_ORIGINS there is
    empty by default and this extra check is a no-op.
    """
    host = request.get_host()
    trusted_netlocs = {urlparse(o).netloc for o in settings.CSRF_TRUSTED_ORIGINS}

    origin = request.headers.get("Origin")
    if origin:
        netloc = urlparse(origin).netloc
        return netloc == host or netloc in trusted_netlocs
    referer = request.headers.get("Referer")
    if referer:
        netloc = urlparse(referer).netloc
        return netloc == host or netloc in trusted_netlocs
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
