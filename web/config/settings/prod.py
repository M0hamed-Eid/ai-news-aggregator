"""Production settings. Run with DJANGO_SETTINGS_MODULE=config.settings.prod."""
from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = False

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

# No MEDIA_ROOT/MEDIA_URL on purpose — this app has zero file-upload/media
# features (confirmed via repo-wide grep before writing this deployment
# plan). Revisit only if a future milestone adds user-uploaded files.
#
# M15 — still no CORS package, even though a separate Next.js `frontend`
# service now serves most pages (see docker/docker-compose.prod.yml +
# Caddyfile). Caddy path-routes both services under ONE domain, so the
# browser only ever sees a single origin — the frontend's fetch calls
# (frontend/src/lib/api.ts) are same-origin requests, not cross-origin
# ones, and Django's existing session-cookie + CSRF-cookie auth model
# (CSRF_TRUSTED_ORIGINS below) needs no changes at all.

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
