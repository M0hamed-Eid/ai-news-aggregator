"""
Base settings shared by every environment.
Environment-specific overrides live in dev.py and prod.py.
"""
from pathlib import Path

import environ
from django.contrib.messages import constants as message_constants

# web/config/settings/base.py -> parents[2] == web/
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
)

# Load web/.env (does NOT read the pipeline's root .env).
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "apps.accounts",
    "apps.onboarding",  # persona/interest/digest-settings, depends on accounts
    "apps.behavior",  # user_events/saved_items (M7), depends on accounts
    "apps.catalog",  # read-only, pipeline-owned tables
    "apps.news",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.EnsureUserProfileMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# -----------------------------------------------------------------------------
# Database — the SAME PostgreSQL the pipeline uses.
# Django owns only its own tables; the pipeline stays the owner of
# `articles` and `youtube_videos`. Django never migrates those tables.
# -----------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# Routes the read-only `catalog` app and blocks migrations on pipeline tables.
DATABASE_ROUTERS = ["config.routers.PipelineRouter"]

# -----------------------------------------------------------------------------
# Cache — Redis, same instance the pipeline's Celery uses (see M6's
# docker/docker-compose.yml `redis` service), but a SEPARATE logical DB index
# (1, not 0) so Django's cache entries never collide with Celery's broker/
# result-backend keys. Used for rate-limiting the event ingestion endpoint
# (apps.behavior) — the default LocMemCache is per-process and would not
# correctly enforce a shared limit across multiple gunicorn workers.
# -----------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://127.0.0.1:6379/1"),
    }
}

# M9 — semantic search's query-embedding Celery client (web/apps/news/search.py)
# needs the PIPELINE's broker/backend DB (0), which is DELIBERATELY a
# different env var from CACHES' own REDIS_URL above (DB 1) — reusing
# REDIS_URL for both would repeat the exact DB-index collision class
# already documented in .wolf/buglog.json (pipeline-015): two processes,
# two different intended Redis DBs, same-looking env var name.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Map Django's ERROR message tag to Bootstrap's "danger" alert class.
MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# Auth flow routing (URL pattern names).
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

# M13 — verification/password-reset emails, via Django's OWN mail
# infrastructure (separate from the pipeline's Gmail-based EmailSender,
# app/services/email_sender.py, which sends digest emails from an entirely
# different process). Reuses the SAME GMAIL_ADDRESS/GMAIL_APP_PASSWORD
# credentials EmailSender already uses, if present in web/.env, so real
# mail actually lands in an inbox instead of only printing to the dev
# server's console. Falls back to the console backend when no credentials
# are configured — same graceful-degradation discipline as EmailSender's
# own is_configured check, never crashes on a missing credential.
GMAIL_ADDRESS = env("GMAIL_ADDRESS", default="")
GMAIL_APP_PASSWORD = env("GMAIL_APP_PASSWORD", default="")
if GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 465
    EMAIL_USE_SSL = True
    EMAIL_HOST_USER = GMAIL_ADDRESS
    EMAIL_HOST_PASSWORD = GMAIL_APP_PASSWORD
    # Must be the authenticated Gmail address (or a same-domain alias) —
    # Gmail's own SPF/DKIM will flag or rewrite a From header claiming an
    # unrelated domain (e.g. "noreply@aicompass.local") sent through its SMTP.
    DEFAULT_FROM_EMAIL = f"AI Compass <{GMAIL_ADDRESS}>"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "AI Compass <noreply@aicompass.local>"

# M13 — Stripe (test mode). All blank-by-default: apps.accounts.billing
# checks these before doing anything and degrades to an honest "billing
# isn't configured" state rather than crashing (same discipline as
# EnrichmentAgent's Groq/Ollama fallback).
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_PRICE_ID_PRO = env("STRIPE_PRICE_ID_PRO", default="")
