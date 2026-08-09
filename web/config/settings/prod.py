"""Production settings. Run with DJANGO_SETTINGS_MODULE=config.settings.prod."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = False

# base.py's env.Env() declares a (list, ["127.0.0.1", "localhost"]) default
# for DJANGO_ALLOWED_HOSTS so plain `manage.py runserver` works with zero
# config in dev — but that same silent default is dangerous in prod: if the
# Render dashboard env var is ever left blank, every real request just 400s
# with no obvious cause (found during the production-readiness audit).
# Require it explicitly here instead of inheriting base.py's fallback.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=None)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must be set in production (e.g. "
        "\"your-app.onrender.com\") — refusing to silently fall back to "
        "127.0.0.1/localhost, which would 400 every real request."
    )

# Serve compressed, hashed static files via WhiteNoise.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Security hardening — assumes HTTPS termination at the proxy.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=2592000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Django 4+ requires the real scheme+host explicitly once behind HTTPS —
# ALLOWED_HOSTS alone isn't enough for POST/CSRF checks (login, source
# submission, Stripe checkout redirect, etc.). Comma-separated, full
# origins including scheme, e.g. "https://app.example.com,https://example.com".
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Found live on Render (2026-08-09): VerifyEmailView/CheckoutSuccessView/
# CheckoutCancelView all did `redirect("/")`/`redirect("/login")`/
# `redirect("/billing")`/`redirect("/pricing")` — relative paths on
# DJANGO's own domain, which 404 on a split-domain deploy since Django is
# API+admin only here (those pages only exist on the Vercel frontend).
# Confirmed via a real emailed verification link: GET .../verify/... ->
# 302 to Django's own "/" -> 404. Empty by default (genuine no-op on the
# same-origin Oracle/Caddy path, where the existing relative redirects
# are already correct) — set only for the Vercel+Render split. See
# apps.accounts.views.frontend_redirect, the shared helper both views use.
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="").rstrip("/")

# No MEDIA_ROOT/MEDIA_URL on purpose — this app has zero file-upload/media
# features (confirmed via repo-wide grep before writing this deployment
# plan). Revisit only if a future milestone adds user-uploaded files.
#
# M16 — CORS + cross-origin cookies, for the Vercel (frontend) / Render
# (backend) split-domain deploy. The Oracle path (Caddy, one domain) still
# needs none of this — CORS_ALLOWED_ORIGINS defaults to empty, which is a
# genuine no-op (a same-origin browser request is never subject to CORS
# checks in the first place), so leaving these unset on that path changes
# nothing about its behavior.
#
# Explicit allowlist ONLY — never CORS_ALLOW_ALLOW_ORIGINS=True combined
# with credentials, which is a real, serious misconfiguration (any site
# could then read a logged-in user's session). CORS_ALLOW_CREDENTIALS is
# required because the frontend authenticates via session+CSRF cookies
# (frontend/src/lib/api.ts's `credentials: 'include'`), not a bearer token.
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# Cross-site cookies require SameSite=None (Lax/Strict, the Django default,
# blocks a cookie from EVER being sent on a cross-origin request — which is
# exactly what every Vercel->Render call is). This is not a weakening of
# security: None-without-Secure would be, but SESSION_COOKIE_SECURE/
# CSRF_COOKIE_SECURE are already True above, so the cookie is still only
# ever sent over HTTPS, and CSRF_TRUSTED_ORIGINS + CsrfViewMiddleware still
# enforce the actual CSRF protection — SameSite is defense-in-depth on top
# of that, not instead of it. Harmless on the same-origin Oracle path too:
# SameSite has no effect on same-origin requests at all.
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO"), "propagate": False},
    },
}
