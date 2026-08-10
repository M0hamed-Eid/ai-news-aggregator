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
    "apps.assistant",  # M14 — RAG chat assistant, depends on catalog (read-only) + accounts (entitlements)
    "corsheaders",  # M16 — Vercel<->Render split-domain deploy, see settings/prod.py
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # As high as practical per django-cors-headers' own install docs — must
    # run before CommonMiddleware so it can add CORS headers to that
    # middleware's redirect responses too. A no-op in the same-origin Oracle
    # deployment (CORS_ALLOWED_ORIGINS is empty there, see prod.py).
    "corsheaders.middleware.CorsMiddleware",
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

# Auth flow routing — literal SPA paths, not Django URL names. M15 retired
# the classic accounts:login/home template views the SPA (frontend/) now
# owns those routes entirely; every LoginRequiredMixin-gated JSON API view
# (ProfileAPIView, BillingAPIView, OpsAPIView, etc.) still consults
# LOGIN_URL as its anonymous-request fallback, so this must resolve without
# reverse() ever touching a deleted URL name.
LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# M13 — verification/password-reset emails, via Django's OWN mail
# infrastructure (separate from the pipeline's Gmail-based EmailSender,
# app/services/email_sender.py, which sends digest emails from an entirely
# different process).
#
# Priority: Gmail API (OAuth) > Resend (HTTP API) > Gmail SMTP > console.
# Confirmed LIVE on Render (2026-08-09) that Gmail SMTP is unusable there
# at all -- not a timeout/misconfig, a hard OSError: [Errno 101] Network
# is unreachable connecting to smtp.gmail.com:465, meaning Render has no
# outbound route for raw SMTP whatsoever. Resend and the Gmail API both
# send over plain HTTPS instead (see config/email_backends.py), which
# obviously works since the whole app already runs over HTTPS.
#
# Gmail API ranks above Resend: found live during the 2026-08-10 QA pass
# that Resend's sandbox mode (no verified domain, and buying one was
# declined) only delivers to the account owner's own exact address --
# every other real signup got no email at all. An OAuth-authorized Gmail
# account can send to any recipient with zero domain-verification step,
# at the cost of a one-time OAuth consent flow instead of DNS records --
# see scripts/get_gmail_refresh_token.py for that one-time setup.
#
# Gmail SMTP is kept as the fallback specifically for the Oracle/Caddy
# deployment path (docs/DEPLOYMENT.md), which has real persistent compute
# and a normal outbound network with no such platform-level SMTP
# restriction -- don't rip it out just because Render can't use it.
GMAIL_OAUTH_CLIENT_ID = env("GMAIL_OAUTH_CLIENT_ID", default="")
GMAIL_OAUTH_CLIENT_SECRET = env("GMAIL_OAUTH_CLIENT_SECRET", default="")
GMAIL_OAUTH_REFRESH_TOKEN = env("GMAIL_OAUTH_REFRESH_TOKEN", default="")
RESEND_API_KEY = env("RESEND_API_KEY", default="")
GMAIL_ADDRESS = env("GMAIL_ADDRESS", default="")
GMAIL_APP_PASSWORD = env("GMAIL_APP_PASSWORD", default="")

if GMAIL_OAUTH_CLIENT_ID and GMAIL_OAUTH_CLIENT_SECRET and GMAIL_OAUTH_REFRESH_TOKEN and GMAIL_ADDRESS:
    EMAIL_BACKEND = "config.email_backends.GmailAPIEmailBackend"
    # Must be the Gmail address the OAuth consent was granted for --
    # same SPF/DKIM constraint as the SMTP branch below.
    DEFAULT_FROM_EMAIL = f"AI Compass <{GMAIL_ADDRESS}>"
elif RESEND_API_KEY:
    EMAIL_BACKEND = "config.email_backends.ResendEmailBackend"
    # Resend's own sandbox sender, valid with zero domain setup -- works
    # immediately on signup. Override once a custom domain is verified in
    # the Resend dashboard (RESEND_FROM_EMAIL="AI Compass <noreply@yourdomain>").
    DEFAULT_FROM_EMAIL = env("RESEND_FROM_EMAIL", default="AI Compass <onboarding@resend.dev>")
elif GMAIL_ADDRESS and GMAIL_APP_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 465
    EMAIL_USE_SSL = True
    EMAIL_HOST_USER = GMAIL_ADDRESS
    EMAIL_HOST_PASSWORD = GMAIL_APP_PASSWORD
    # A short timeout so an unreachable/filtered SMTP port fails in
    # seconds rather than hanging until gunicorn's own request timeout
    # SIGKILLs the worker -- see PasswordResetRequestAPIView's
    # accompanying try/except for the other half of this: a failed send
    # degrades to a logged warning, never a 500.
    EMAIL_TIMEOUT = 10
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

# M14 Phase D — the ONE disclosed exception to "web/ is LLM-free": a direct
# Groq client used ONLY for streaming chat generation (apps.assistant.
# llm_client), since Celery's request/response boundary can't stream tokens.
# Retrieval still crosses to the pipeline via Celery either way. Blank by
# default; apps.assistant.llm_client.is_configured() gates the streaming
# endpoint on this, same degrade-honestly discipline as Stripe/Gmail above —
# the non-streaming endpoint (AssistantMessageView) works with zero setup.
GROQ_API_KEY = env("GROQ_API_KEY", default="")
# M16 — multi-key failover (apps.assistant.llm_client._load_groq_keys()).
# Numbered keys are entirely optional: with none set, behavior is exactly
# what it was before this existed (single GROQ_API_KEY, no failover). Fixed
# count (not a dynamic scan) because Django settings are static at import
# time — 5 is a generous ceiling for "yourself and your teammates" without
# needing a settings-schema change if someone adds a 6th key later than
# expected (it would just be silently unused; documented in .env.example).
GROQ_API_KEY_1 = env("GROQ_API_KEY_1", default="")
GROQ_API_KEY_2 = env("GROQ_API_KEY_2", default="")
GROQ_API_KEY_3 = env("GROQ_API_KEY_3", default="")
GROQ_API_KEY_4 = env("GROQ_API_KEY_4", default="")
GROQ_API_KEY_5 = env("GROQ_API_KEY_5", default="")
