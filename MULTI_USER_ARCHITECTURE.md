# Multi-User Platform — Architecture, Design & Implementation Guide

> **Goal:** Evolve the single-user AI News Aggregator into a multi-user platform with authentication (manual + Google/GitHub/Microsoft OAuth), secure sessions, password reset, and a two-step onboarding flow (persona + interests) — designed so future personalized ranking can use these preferences.
>
> **Scope of THIS phase:** Build the user system + onboarding + storage only. No personalization logic yet — but the schema is built to make that trivial later.
>
> **Two architectural decisions already locked (with reasoning in §1.4):**
> 1. **One shared PostgreSQL database. Django ORM owns the user/auth tables; the existing pipeline keeps SQLAlchemy for content tables.** Zero rewrite of the working pipeline — lowest risk.
> 2. **Django server-rendered pages + `django-allauth`** for all auth and onboarding. Fewest moving parts, best Django developer experience, ideal for a graduation project.

---

## 0. Challenging your assumptions & architectural risks (read this first)

You asked me to be opinionated and challenge the requirements. Here are the things I'd push back on *before* writing a line of code:

**R1 — Microsoft OAuth is disproportionately expensive to set up.** Google and GitHub OAuth take ~10 minutes each. Microsoft (Azure AD / Entra ID) requires an Azure tenant, an app registration, redirect URIs, and tenant-type decisions (single vs multi-tenant). For a graduation project this is a lot of friction for little payoff. **Recommendation:** ship Google + GitHub first (they cover ~95% of your likely users), and add Microsoft as an *optional* provider once the rest works. `django-allauth` makes adding it later a config-only change, so nothing is lost. I include the Microsoft config so you *can* enable it — I just wouldn't block the project on it.

**R2 — "Persist sessions securely" does not mean build JWT.** A common student instinct is to reach for JWT/token auth. For a server-rendered Django app you do **not** want that — Django's signed, server-side session cookies (which allauth uses) are more secure and simpler than hand-rolled JWT. Building JWT here would be overengineering and a security risk. We use Django sessions + secure cookie flags.

**R3 — The real deployment risk is Playwright, not Django.** Your pipeline drives headless Chromium (for Anthropic). Free web hosts (Render free tier) struggle to run Chromium reliably and it bloats the image. **Mitigation (and a clean architecture win):** split responsibilities — the **web app** (Django, no browser needed) deploys to a free web host; the **pipeline** (scraping + LLM + email, needs Chromium) runs on **GitHub Actions cron**, which has Chromium support and 2,000 free minutes/month. They share the one database. This separation is also better engineering: a slow nightly batch job should never live inside your request/response web process.

**R4 — Two ORMs on one database is a minor smell; manage it explicitly.** Django ORM and SQLAlchemy will both point at the same Postgres. The rule that keeps this clean: **each ORM owns its own tables and never migrates the other's.** Django manages `auth_*`, `accounts_*`, `onboarding_*`. SQLAlchemy manages `articles`, `youtube_videos`. We tell Django *not* to manage the content tables. Long-term, if you ever want a single ORM, the migration path is to move content models into Django ORM — but that's explicitly out of scope and unnecessary now.

**R5 — Don't fork the data model for "future personalization" prematurely.** You said personalization comes later. We design for it with two cheap, forward-looking touches: (a) a `weight` field on the user↔interest link, and (b) `persona`/`interest` as **lookup tables** (not hard-coded enums) so you can later attach ranking metadata to them. We do **not** build a scoring engine, feature store, or per-user model now. That would be overengineering.

**R6 — Render's free PostgreSQL expires after 90 days.** Don't use it as your real DB. Use **Neon** (free, persistent Postgres, no expiry) as the single shared database for both the web app and the GitHub Actions pipeline. Details in §6.

**R7 — Email is already solved — reuse it.** Password reset and allauth email verification both need SMTP. You already have working Gmail SMTP (`app/services/email_sender.py` uses `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`). Django reuses the same credentials via its email backend — no new service needed.

Everything below assumes you accept R1–R7. If you disagree with any, tell me and I'll adjust.

---

# Phase 1 — Architecture Design

## 1.1 The recommended architecture in one picture

```mermaid
flowchart TB
    subgraph User["End users (browsers)"]
        Br[Browser]
    end

    subgraph Web["Django Web App  (free web host, e.g. Render)"]
        ALL["django-allauth<br/>signup / login / logout<br/>password reset / OAuth"]
        ACC["accounts app<br/>custom User + Profile"]
        ONB["onboarding app<br/>persona + interests"]
        DASH["dashboard views"]
        WN["WhiteNoise static files"]
    end

    subgraph Pipeline["Existing pipeline  (GitHub Actions cron)"]
        RP["run_pipeline.py / mgmt command"]
        SCR["scrapers (Playwright/RSS)"]
        AG["Groq agents"]
        ES["EmailSender (Gmail SMTP)"]
    end

    subgraph Data["Single shared PostgreSQL  (Neon, free)"]
        TUSER[("Django tables:<br/>users, profiles,<br/>personas, interests")]
        TCONTENT[("Pipeline tables:<br/>articles,<br/>youtube_videos")]
    end

    Br -->|HTTPS| ALL
    Br --> DASH
    ALL --> ACC --> ONB --> DASH
    ACC -->|Django ORM| TUSER
    ONB -->|Django ORM| TUSER
    RP --> SCR --> TCONTENT
    RP --> AG
    RP -->|reads prefs later| TUSER
    AG --> ES
    Br -. OAuth .-> G[Google]
    Br -. OAuth .-> GH[GitHub]
    Br -. OAuth .-> MS[Microsoft]
```

**The mental model:** two processes, one database.
- The **web app** is online 24/7 and handles humans (auth, onboarding, dashboard). It never scrapes or calls an LLM.
- The **pipeline** wakes on a schedule, does the heavy ETL+LLM+email work, and goes back to sleep. It never serves web requests.
- They communicate **only through the shared database**, which is the cleanest possible coupling.

## 1.2 New components introduced

| Component | Type | Responsibility |
|-----------|------|----------------|
| `core/` | Django project (settings) | Settings, root URLs, WSGI/ASGI. |
| `accounts` app | Django app | Custom `User` (email login), `UserProfile`, admin, auth wiring. |
| `onboarding` app | Django app | `Persona`, `Interest`, `UserInterest` models; two-step onboarding views/forms; gate middleware. |
| `django-allauth` | Library | Manual signup/login/logout, password reset, email verification, **and** Google/GitHub/Microsoft OAuth — all in one. |
| `templates/` | Server-rendered HTML | allauth overrides + onboarding + dashboard pages. |
| WhiteNoise | Library | Serves static files (CSS) directly from Django — no separate static host. |
| GitHub Actions workflow | CI/cron | Runs the existing pipeline nightly. |
| `manage.py` | Django CLI | Migrations, runserver, custom commands. |

## 1.3 How Django integrates with the current pipeline

Nothing in `app/` is rewritten. Django is added *around* it in the same repository (a monorepo). The integration contract is the database:

```mermaid
flowchart LR
    subgraph Repo["One Git repository"]
        subgraph existing["app/  (UNCHANGED)"]
            P1[scrapers]
            P2[agents]
            P3[services]
            P4[SQLAlchemy models<br/>articles, youtube_videos]
        end
        subgraph new["NEW Django code"]
            D1[core/ settings]
            D2[accounts/]
            D3[onboarding/]
        end
    end
    P4 -->|owns| CT[(content tables)]
    D2 -->|owns| UT[(user tables)]
    D3 -->|owns| UT
    CT --- PG[(Neon PostgreSQL)]
    UT --- PG
```

**Migration path for the pipeline (staged, non-breaking):**
1. **Now:** Add Django + user tables. Pipeline keeps running exactly as today (single-user, profile from `config.py`). ✅ Nothing breaks.
2. **Later (out of scope):** Wrap `run_pipeline.py` as a Django management command (`python manage.py run_digest`) so the pipeline gets Django ORM access to user prefs while keeping SQLAlchemy for content. I include this command in Phase 4 as an *optional* bridge so it's ready.
3. **Future personalization:** The curator agent reads each user's persona + weighted interests from the Django tables and ranks per-user. The schema already supports this.

## 1.4 Why this architecture (the decision record)

**Why Django at all (vs Flask/FastAPI)?** You have Django experience, and this feature set — user accounts, admin, sessions, password reset, OAuth, server-rendered forms — is *exactly* Django's batteries-included sweet spot. allauth alone saves you weeks. FastAPI would mean building all of that by hand. **Django is the correct choice here, not just the familiar one.**

**Why "coexist, shared DB" (vs migrating the pipeline to Django ORM)?** The pipeline works and is tested against SQLAlchemy + Postgres. Rewriting 1,500+ lines of working scraper/agent/repository code into Django ORM adds large risk for zero user-facing benefit right now, and directly violates your "don't break current functionality" constraint. Each ORM owning its own tables is a well-trodden pattern (web app + ETL worker sharing a DB).

**Why server-rendered + allauth (vs DRF + SPA)?** A REST API + React frontend doubles the surface area (two apps, two deploys, CORS, token handling) for a project whose UI is just login + a 2-step form + a dashboard. Server-rendered Django templates ship in a fraction of the time and are far easier to defend. If you ever want a SPA, allauth has a headless/API mode you can switch on later.

**Why split web vs pipeline across two hosts?** See R3 — Playwright/Chromium doesn't belong in a free web dyno, and a nightly batch job doesn't belong in a request-serving process. The split is both a cost fix and a clean-architecture win.

---

# Phase 2 — Database Design

## 2.1 The full schema

```mermaid
erDiagram
    USER ||--|| USERPROFILE : "has one"
    PERSONA ||--o{ USERPROFILE : "categorizes"
    USERPROFILE ||--o{ USERINTEREST : "has many"
    INTEREST ||--o{ USERINTEREST : "chosen by"

    USER {
        bigint id PK
        string email UK "login identifier, unique"
        string name "display name"
        string password "hashed (PBKDF2)"
        bool is_active
        bool is_staff
        datetime date_joined
        datetime last_login
    }
    USERPROFILE {
        bigint id PK
        bigint user_id FK "OneToOne -> USER"
        bigint persona_id FK "nullable -> PERSONA"
        bool onboarding_completed "default false"
        datetime created_at
        datetime updated_at
    }
    PERSONA {
        bigint id PK
        string slug UK "student, teacher, ..."
        string name "display label"
        string description
        int sort_order
        bool is_active
    }
    INTEREST {
        bigint id PK
        string slug UK "machine-learning, nlp, ..."
        string name "display label"
        string category "nullable grouping"
        int sort_order
        bool is_active
    }
    USERINTEREST {
        bigint id PK
        bigint profile_id FK "-> USERPROFILE"
        bigint interest_id FK "-> INTEREST"
        float weight "default 1.0 (future ranking)"
        datetime created_at
    }
```

## 2.2 Each table — what it is and why it exists

### `User` (app: `accounts`) — **custom user, email as login**
**Why a custom user instead of Django's default?** Django's default `User` uses `username` as the login field. Your requirement is email login. The clean, Django-blessed way is a custom user model with `USERNAME_FIELD = "email"`. **This must be done at the very start of the project** — switching the user model after migrations exist is extremely painful. So this is step 1 in the roadmap.

It stores: `email` (unique, the login id), `name` (display), hashed `password` (PBKDF2 by default — never plaintext), and Django's standard flags (`is_active`, `is_staff`, `date_joined`, `last_login`). OAuth identities are stored by allauth in its own `socialaccount_*` tables and linked to this `User` — we don't reinvent that.

### `UserProfile` (app: `accounts`) — **per-user app data, 1:1 with User**
**Why separate from User?** Keep authentication concerns (`User`) apart from product/profile concerns (`UserProfile`). This is a standard Django pattern and means we never have to touch the auth model to add profile fields. It holds the `persona` foreign key, the `onboarding_completed` flag (drives the onboarding gate), and timestamps. A profile row is auto-created for every user via a signal, so it always exists.

### `Persona` (app: `onboarding`) — **lookup table, not an enum**
**Why a table instead of Python choices?** You listed 7 fixed personas, so an enum would *work*. But a lookup table is the better forward-looking choice because: (a) you can add/rename/deactivate personas without a code deploy + migration, and (b) **future personalization** can hang metadata off each persona (e.g., default interest weights, a ranking-prompt snippet) without schema churn. It's seeded once via a data migration. Cost of this choice is one extra join — negligible.

### `Interest` (app: `onboarding`) — **lookup table of topics**
Same reasoning as Persona. Holds the 15 example interests (Machine Learning, NLP, LLMs, …) with a `slug` (stable key), `name` (display), optional `category` (for grouping in the UI later), `sort_order`, and `is_active`. Seeded via data migration.

### `UserInterest` (app: `onboarding`) — **the M2M link with a future-proof `weight`**
**Why an explicit through table instead of a plain `ManyToManyField`?** Because you told me ranking will use these later. A plain M2M can only record "user likes interest." A through table adds a **`weight` float (default 1.0)** — so future ranking can say "this user cares about LLMs at 1.0 but Robotics at 0.3," or let the system *learn* weights from behavior. Adding `weight` now (cheap) avoids a painful M2M-to-through migration later. This single decision is what makes the schema "designed with future personalization in mind."

## 2.3 How future ranking will consume this (design intent)

The curator agent currently builds its prompt from `config.UserProfile` (`app/config.py`). Later, for a given recipient, it will instead load:

```text
persona        = user.profile.persona.name              # e.g. "ML Engineer"
weighted_terms = [(ui.interest.name, ui.weight)         # e.g. [("LLMs",1.0),("RAG",0.8)]
                  for ui in user.profile.interests.all()]
```

…and inject `persona` + `weighted_terms` into the ranking system prompt. Because interests carry weights and personas can carry ranking metadata, **no schema change** is needed when you build personalization — only agent-prompt changes. That's the whole point of this design.

## 2.4 Relationships summary

- `User 1—1 UserProfile` (OneToOne, cascade delete).
- `Persona 1—* UserProfile` (a persona categorizes many profiles; nullable until onboarding done).
- `UserProfile 1—* UserInterest *—1 Interest` (many-to-many through `UserInterest`, carrying `weight`).
- OAuth: allauth's `SocialAccount *—1 User` (managed by allauth, not us).

## 2.5 Migration strategy

1. **Schema migrations are owned by Django**, generated with `makemigrations` and applied with `migrate`. They only ever touch Django tables.
2. **The existing content tables (`articles`, `youtube_videos`) are invisible to Django migrations.** We never create Django models for them (or if we ever do for read access, we mark them `managed = False` so Django won't try to create/alter/drop them). SQLAlchemy's `create_tables.py` remains the source of truth for those two tables.
3. **Seed data (personas + interests) ships as data migrations** (not fixtures run by hand) so a fresh deploy is fully reproducible with a single `migrate`.
4. **Ordering:** (a) create the custom user model migration *first*, before any `migrate` is ever run, (b) then profile + onboarding models, (c) then data migrations to seed lookups. The roadmap in Phase 3 enforces this order.
5. **Rollback:** every migration is reversible; data migrations include reverse functions that delete seeded rows.
6. **No Alembic involvement** — Alembic (declared in `pyproject.toml` but unused) stays unused; Django's migration framework handles all new tables.

---

# Phase 3 — Implementation Roadmap (easiest → hardest)

Each step is independently testable. Do them in order; do not start a step until the previous one runs.

| # | Step | Objective | Files to CREATE | Files to MODIFY | Expected outcome |
|---|------|-----------|-----------------|-----------------|------------------|
| 0 | **Install & scaffold** | Get Django + allauth installed and a project skeleton next to `app/`. | `manage.py`, `core/{__init__,settings,urls,wsgi,asgi}.py`, `requirements-web.txt` | `pyproject.toml`, `.env`, `.gitignore` | `python manage.py check` passes. |
| 1 | **Custom User (do first!)** | Email-as-login user before any migration runs. | `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/managers.py`, `accounts/admin.py` | `core/settings.py` (`AUTH_USER_MODEL`) | `migrate` creates `accounts_user`; superuser logs in by email. |
| 2 | **Profile + signal** | Auto-create a profile per user. | (extend `accounts/models.py`, `accounts/signals.py`) | `accounts/apps.py` | New users get a `UserProfile` row automatically. |
| 3 | **allauth manual auth** | Signup/login/logout/password reset with email. | `templates/account/*.html`, `templates/base.html` | `core/settings.py`, `core/urls.py` | You can register, log in, log out, reset password locally. |
| 4 | **Onboarding models + seed** | Persona/Interest/UserInterest tables + seeded data. | `onboarding/{__init__,apps,models,admin}.py`, `onboarding/migrations/0002_seed_lookups.py` | `core/settings.py` (INSTALLED_APPS) | Tables exist; 7 personas + 15 interests seeded. |
| 5 | **Onboarding flow + gate** | Two-step form; force new users through it. | `onboarding/{forms,views,urls}.py`, `onboarding/middleware.py`, `templates/onboarding/*.html`, `templates/dashboard.html` | `core/settings.py` (middleware), `core/urls.py` | After first login → persona step → interests step → dashboard; completed users skip it. |
| 6 | **OAuth providers** | Google + GitHub (Microsoft optional). | (none) | `core/settings.py` (providers), `.env` | "Sign in with Google/GitHub" works. |
| 7 | **Pipeline bridge (optional)** | Make the pipeline runnable as a Django command for future personalization. | `accounts/management/commands/run_digest.py` | (none) | `python manage.py run_digest` runs the existing pipeline. |
| 8 | **Deploy** | Web on free host, pipeline on GH Actions, DB on Neon. | `build.sh`, `render.yaml`, `.github/workflows/pipeline.yml` | `core/settings.py` (prod settings) | Public URL with working auth; nightly pipeline. |

---

# Phase 4 — Code Generation (complete, sequential)

> Follow these in order. Every file is shown in full. Commands are exact. The new web code lives at the **repo root** alongside the existing `app/` package — they do not collide (Django apps are independent of your `app/` pipeline package).

## Step 0 — Install & scaffold

**Why:** We need Django, allauth, the Postgres driver, WhiteNoise, and dotenv before anything else. We keep web dependencies in their own file so the pipeline's `pyproject.toml` stays focused.

**Package installation (commands):**
```bash
# from the repo root, with your venv active
pip install "Django>=5.0,<5.2" "django-allauth[socialaccount]>=65.0" \
            psycopg2-binary dj-database-url python-dotenv whitenoise gunicorn
pip freeze > requirements-web.txt
```

**Create the project skeleton** (we create files by hand rather than `django-admin startproject` so they match exactly):

`manage.py`
```python
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH? Did you forget to activate a venv?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`core/__init__.py` — empty file.

`core/settings.py`
```python
# core/settings.py
"""
Django settings for the multi-user web layer.

Coexists with the existing SQLAlchemy pipeline in app/.
Django owns the user/auth/onboarding tables; it never touches
the pipeline's `articles` / `youtube_videos` tables.
"""
from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # reuse the same .env as the pipeline

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",                 # required by allauth

    # third-party
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "allauth.socialaccount.providers.microsoft",

    # local
    "accounts",
    "onboarding",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",          # static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",        # required by allauth
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "onboarding.middleware.OnboardingRequiredMiddleware",  # our gate (step 5)
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ---------------------------------------------------------------------------
# Database — ONE shared PostgreSQL. Django manages only its own tables.
# Locally falls back to the same POSTGRES_* vars the pipeline uses.
# ---------------------------------------------------------------------------
DEFAULT_DB_URL = (
    f"postgres://{os.getenv('POSTGRES_USER', 'ai_news_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'changeme_in_production')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'ai_news')}"
)
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", DEFAULT_DB_URL),
        conn_max_age=600,
        ssl_require=os.getenv("DJANGO_DB_SSL", "False").lower() == "true",
    )
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",       # admin / Django auth
    "allauth.account.auth_backends.AuthenticationBackend",  # allauth
]

LOGIN_REDIRECT_URL = "/onboarding/"      # gate decides next stop
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# django-allauth configuration (modern settings format)
# ---------------------------------------------------------------------------
ACCOUNT_LOGIN_METHODS = {"email"}                  # log in with email, no username
ACCOUNT_SIGNUP_FIELDS = ["email*", "name*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None           # our user has no username
ACCOUNT_EMAIL_VERIFICATION = "optional"            # set "mandatory" in prod if desired
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_RATE_LIMITS = {"login_failed": "5/5m"}     # basic brute-force protection

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
    "github": {
        "APP": {
            "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
            "secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
        },
        "SCOPE": ["read:user", "user:email"],
    },
    "microsoft": {   # optional — see risk R1
        "APP": {
            "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
            "secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        },
        "TENANT": os.getenv("MICROSOFT_TENANT", "common"),
    },
}

# ---------------------------------------------------------------------------
# Email — reuse the pipeline's Gmail SMTP for password reset + verification
# ---------------------------------------------------------------------------
if os.getenv("GMAIL_ADDRESS") and os.getenv("GMAIL_APP_PASSWORD"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.getenv("GMAIL_ADDRESS")
    EMAIL_HOST_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
    DEFAULT_FROM_EMAIL = os.getenv("GMAIL_ADDRESS")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # dev: print to console

# ---------------------------------------------------------------------------
# Static files (WhiteNoise — no separate host needed)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Security (tightened automatically when DEBUG is off)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 2592000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
```

`core/urls.py`
```python
# core/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),     # login, logout, signup, reset, oauth
    path("onboarding/", include("onboarding.urls")),
    path("dashboard/", include("onboarding.dashboard_urls")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]
```

`core/wsgi.py`
```python
# core/wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
application = get_wsgi_application()
```

`core/asgi.py`
```python
# core/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
application = get_asgi_application()
```

**Environment variables to add to `.env`** (append; keep existing pipeline vars):
```bash
# --- Django web layer ---
DJANGO_SECRET_KEY=generate-a-50-char-random-string
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=
DJANGO_DB_SSL=False
# DATABASE_URL is already used by your pipeline; Django reuses it.

# --- OAuth (fill after Phase 6 provider setup) ---
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT=common
```
Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

**Add to `.gitignore`** (if not already): `staticfiles/`.

**Test Step 0:**
```bash
python manage.py check        # should report no issues (DB not required yet)
```

## Step 1 — Custom User (do this BEFORE the first migrate)

**Why:** Email login requires a custom user model, and Django demands it be set before the initial migration. Doing this first avoids the notoriously painful mid-project user-model swap.

`accounts/__init__.py` — empty.

`accounts/apps.py`
```python
# accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        # Register signals (profile auto-creation) — added in Step 2.
        from . import signals  # noqa: F401
```

`accounts/managers.py`
```python
# accounts/managers.py
from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for a user model that logs in with email instead of username."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)   # hashes with PBKDF2
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)
```

`accounts/models.py` (User + Profile together — Profile detailed in Step 2)
```python
# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user: email is the unique login identifier; no username."""

    email = models.EmailField("email address", unique=True)
    name = models.CharField("full name", max_length=200, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []          # email + password are required by default

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.name or self.email

    def get_short_name(self) -> str:
        return self.name.split(" ")[0] if self.name else self.email


class UserProfile(models.Model):
    """
    Per-user product data, kept separate from auth concerns.
    A row is auto-created for every user via a post_save signal.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile"
    )
    persona = models.ForeignKey(
        "onboarding.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiles",
    )
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userprofile"

    def __str__(self) -> str:
        return f"Profile<{self.user.email}>"
```

`accounts/admin.py`
```python
# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User, UserProfile


class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    model = User
    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser",
                                    "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "name", "password1", "password2")}),
    )


admin.site.register(User, UserAdmin)
admin.site.register(UserProfile)
```

> Note: the default `UserCreationForm`/`UserChangeForm` reference `username`. If admin user-creation errors, swap in small custom forms keyed on `email` — I can supply them, but most workflows create users via allauth signup, not admin.

**Set the user model** — already done in `core/settings.py` (`AUTH_USER_MODEL = "accounts.User"`).

**Run the first migration:**
```bash
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser     # logs in with EMAIL
```

**Test Step 1:** `python manage.py runserver`, visit `/admin/`, log in with the superuser email + password.

## Step 2 — Profile auto-creation signal

**Why:** Every user must always have a profile (the onboarding gate and future ranking rely on it). A signal guarantees this on creation, including for OAuth signups.

`accounts/signals.py`
```python
# accounts/signals.py
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile the first time a User is saved."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
```

(`accounts/apps.py` already imports this in `ready()`.) No new migration needed.

**Test Step 2:** in `python manage.py shell`, create a user and confirm `user.profile` exists:
```python
from accounts.models import User
u = User.objects.create_user(email="t@e.com", password="x", name="T")
print(u.profile)   # -> Profile<t@e.com>
```

## Step 3 — Manual auth templates (allauth)

**Why:** allauth provides the views/URLs for signup, login, logout, and password reset; we provide minimal templates so they render with your branding.

`templates/base.html`
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI News Aggregator{% endblock %}</title>
  <style>
    body{font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px;color:#1a1a1a}
    h1{font-size:1.4rem}
    label{display:block;margin:.6rem 0 .2rem;font-weight:600}
    input[type=text],input[type=email],input[type=password]{width:100%;padding:.5rem;border:1px solid #ccc;border-radius:6px}
    button,.btn{display:inline-block;margin-top:1rem;padding:.6rem 1rem;border:0;border-radius:6px;background:#0066cc;color:#fff;cursor:pointer;text-decoration:none}
    .messages{list-style:none;padding:0}.messages li{padding:.5rem;border-radius:6px;background:#eef;margin:.3rem 0}
    .chip{display:inline-block;padding:.4rem .7rem;border:1px solid #ccc;border-radius:20px;margin:.2rem;cursor:pointer}
    .chip input{display:none}.chip.sel{background:#0066cc;color:#fff;border-color:#0066cc}
  </style>
</head>
<body>
  {% if messages %}<ul class="messages">{% for m in messages %}<li>{{ m }}</li>{% endfor %}</ul>{% endif %}
  {% block content %}{% endblock %}
</body>
</html>
```

`templates/account/login.html`
```html
{% extends "base.html" %}
{% block title %}Sign in{% endblock %}
{% block content %}
<h1>Sign in</h1>
<form method="post" action="{% url 'account_login' %}">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Sign in</button>
</form>
<p><a href="{% url 'account_reset_password' %}">Forgot password?</a></p>
<p>No account? <a href="{% url 'account_signup' %}">Sign up</a></p>
<hr>
<p>Or continue with:</p>
<a class="btn" href="{% url 'google_login' %}">Google</a>
<a class="btn" href="{% url 'github_login' %}">GitHub</a>
{% endblock %}
```

`templates/account/signup.html`
```html
{% extends "base.html" %}
{% block title %}Sign up{% endblock %}
{% block content %}
<h1>Create your account</h1>
<form method="post" action="{% url 'account_signup' %}">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Sign up</button>
</form>
<p>Already have an account? <a href="{% url 'account_login' %}">Sign in</a></p>
{% endblock %}
```

`templates/account/logout.html`
```html
{% extends "base.html" %}
{% block content %}
<h1>Sign out</h1>
<form method="post" action="{% url 'account_logout' %}">
  {% csrf_token %}
  <button type="submit">Confirm sign out</button>
</form>
{% endblock %}
```

Password-reset templates (minimal — allauth supplies sensible defaults, but explicit files avoid surprises):

`templates/account/password_reset.html`
```html
{% extends "base.html" %}
{% block content %}
<h1>Reset password</h1>
<form method="post" action="{% url 'account_reset_password' %}">
  {% csrf_token %}{{ form.as_p }}
  <button type="submit">Send reset link</button>
</form>
{% endblock %}
```

`templates/account/password_reset_done.html`
```html
{% extends "base.html" %}
{% block content %}<h1>Check your email</h1>
<p>If an account exists for that address, a reset link is on its way.</p>{% endblock %}
```

**Test Step 3:**
```bash
python manage.py runserver
```
Visit `/accounts/signup/` → create an account → you're redirected toward `/onboarding/`. Try `/accounts/logout/` and `/accounts/password/reset/`. With console email backend, the reset link prints in your terminal.

## Step 4 — Onboarding models + seed data

**Why:** These tables store personas and interests and link them to users with a future-proof `weight`.

`onboarding/__init__.py` — empty.

`onboarding/apps.py`
```python
# onboarding/apps.py
from django.apps import AppConfig


class OnboardingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onboarding"
```

`onboarding/models.py`
```python
# onboarding/models.py
from django.conf import settings
from django.db import models


class Persona(models.Model):
    """Lookup table of user personas (Student, ML Engineer, ...)."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "onboarding_persona"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Interest(models.Model):
    """Lookup table of topic interests (LLMs, NLP, RAG, ...)."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "onboarding_interest"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class UserInterest(models.Model):
    """
    Through table linking a user's profile to an interest.
    `weight` is unused today but lets future ranking prioritise topics
    per user without a schema change.
    """
    profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.CASCADE, related_name="interests"
    )
    interest = models.ForeignKey(
        Interest, on_delete=models.CASCADE, related_name="user_links"
    )
    weight = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "onboarding_userinterest"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "interest"], name="uq_profile_interest"
            )
        ]

    def __str__(self) -> str:
        return f"{self.profile.user.email} → {self.interest.name} ({self.weight})"
```

`onboarding/admin.py`
```python
# onboarding/admin.py
from django.contrib import admin
from .models import Persona, Interest, UserInterest

admin.site.register(Persona)
admin.site.register(Interest)
admin.site.register(UserInterest)
```

**Add `onboarding` to `INSTALLED_APPS`** — already included in the Step 0 settings.

**Generate the schema migration, then write the seed data migration:**
```bash
python manage.py makemigrations onboarding   # creates 0001_initial
```

`onboarding/migrations/0002_seed_lookups.py` (data migration — seeds personas + interests)
```python
# onboarding/migrations/0002_seed_lookups.py
from django.db import migrations

PERSONAS = [
    ("student", "Student"), ("teacher", "Teacher"), ("researcher", "Researcher"),
    ("developer", "Developer"), ("data-scientist", "Data Scientist"),
    ("ml-engineer", "ML Engineer"), ("ai-enthusiast", "General AI Enthusiast"),
]
INTERESTS = [
    ("machine-learning", "Machine Learning"), ("deep-learning", "Deep Learning"),
    ("computer-vision", "Computer Vision"), ("nlp", "NLP"), ("llms", "LLMs"),
    ("ai-agents", "AI Agents"), ("rag", "RAG"), ("automation", "Automation"),
    ("robotics", "Robotics"), ("mlops", "MLOps"),
    ("generative-ai", "Generative AI"), ("open-source-models", "Open Source Models"),
    ("ai-research", "AI Research"), ("startups", "Startups"), ("ai-tools", "AI Tools"),
]


def seed(apps, schema_editor):
    Persona = apps.get_model("onboarding", "Persona")
    Interest = apps.get_model("onboarding", "Interest")
    for i, (slug, name) in enumerate(PERSONAS):
        Persona.objects.update_or_create(slug=slug, defaults={"name": name, "sort_order": i})
    for i, (slug, name) in enumerate(INTERESTS):
        Interest.objects.update_or_create(slug=slug, defaults={"name": name, "sort_order": i})


def unseed(apps, schema_editor):
    apps.get_model("onboarding", "Persona").objects.all().delete()
    apps.get_model("onboarding", "Interest").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("onboarding", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
```

```bash
python manage.py migrate
```

**Test Step 4:** in shell, `from onboarding.models import Persona, Interest; print(Persona.objects.count(), Interest.objects.count())` → `7 15`.

## Step 5 — Onboarding flow + gate middleware

**Why:** New users must complete onboarding before using the app; returning users must skip it. A middleware enforces this centrally instead of decorating every view.

`onboarding/forms.py`
```python
# onboarding/forms.py
from django import forms
from .models import Persona, Interest


class PersonaForm(forms.Form):
    persona = forms.ModelChoiceField(
        queryset=Persona.objects.filter(is_active=True),
        widget=forms.RadioSelect,
        empty_label=None,
    )


class InterestsForm(forms.Form):
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
    )

    def clean_interests(self):
        chosen = self.cleaned_data["interests"]
        if len(chosen) < 1:
            raise forms.ValidationError("Pick at least one interest.")
        return chosen
```

`onboarding/views.py`
```python
# onboarding/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import PersonaForm, InterestsForm
from .models import UserInterest


@login_required
def onboarding_entry(request):
    """Route the user to the right step (or out, if already done)."""
    profile = request.user.profile
    if profile.onboarding_completed:
        return redirect("dashboard")
    if profile.persona_id is None:
        return redirect("onboarding_persona")
    return redirect("onboarding_interests")


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_persona(request):
    profile = request.user.profile
    if request.method == "POST":
        form = PersonaForm(request.POST)
        if form.is_valid():
            profile.persona = form.cleaned_data["persona"]
            profile.save(update_fields=["persona", "updated_at"])
            return redirect("onboarding_interests")
    else:
        form = PersonaForm(initial={"persona": profile.persona_id})
    return render(request, "onboarding/persona.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_interests(request):
    profile = request.user.profile
    if profile.persona_id is None:
        return redirect("onboarding_persona")
    if request.method == "POST":
        form = InterestsForm(request.POST)
        if form.is_valid():
            # Replace any existing selections with the new set (default weight 1.0)
            UserInterest.objects.filter(profile=profile).delete()
            UserInterest.objects.bulk_create([
                UserInterest(profile=profile, interest=i)
                for i in form.cleaned_data["interests"]
            ])
            profile.onboarding_completed = True
            profile.save(update_fields=["onboarding_completed", "updated_at"])
            return redirect("dashboard")
    else:
        form = InterestsForm()
    return render(request, "onboarding/interests.html", {"form": form})


@login_required
def dashboard(request):
    profile = request.user.profile
    interests = profile.interests.select_related("interest").all()
    return render(request, "dashboard.html",
                  {"profile": profile, "interests": interests})
```

`onboarding/urls.py`
```python
# onboarding/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.onboarding_entry, name="onboarding_entry"),
    path("persona/", views.onboarding_persona, name="onboarding_persona"),
    path("interests/", views.onboarding_interests, name="onboarding_interests"),
]
```

`onboarding/dashboard_urls.py`
```python
# onboarding/dashboard_urls.py
from django.urls import path
from . import views

urlpatterns = [path("", views.dashboard, name="dashboard")]
```

`onboarding/middleware.py`
```python
# onboarding/middleware.py
from django.shortcuts import redirect
from django.urls import reverse


class OnboardingRequiredMiddleware:
    """
    Force authenticated users who haven't finished onboarding to the flow.
    Allows auth, onboarding, admin, and static paths through.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not user.is_staff:
            path = request.path
            allowed = (
                path.startswith("/onboarding/")
                or path.startswith("/accounts/")
                or path.startswith("/admin/")
                or path.startswith("/static/")
            )
            profile = getattr(user, "profile", None)
            if profile and not profile.onboarding_completed and not allowed:
                return redirect(reverse("onboarding_entry"))
        return self.get_response(request)
```

`templates/onboarding/persona.html`
```html
{% extends "base.html" %}
{% block title %}Choose your persona{% endblock %}
{% block content %}
<h1>Step 1 of 2 — Who are you?</h1>
<form method="post">{% csrf_token %}
  {% for radio in form.persona %}<div class="chip">{{ radio }}</div>{% endfor %}
  {{ form.persona.errors }}
  <div><button type="submit">Continue →</button></div>
</form>
{% endblock %}
```

`templates/onboarding/interests.html`
```html
{% extends "base.html" %}
{% block title %}Choose interests{% endblock %}
{% block content %}
<h1>Step 2 of 2 — What are you into?</h1>
<p>Select all that apply (at least one).</p>
<form method="post">{% csrf_token %}
  {% for cb in form.interests %}<label class="chip">{{ cb }}</label>{% endfor %}
  {{ form.interests.errors }}
  <div><button type="submit">Finish →</button></div>
</form>
{% endblock %}
```

`templates/dashboard.html`
```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1>Welcome, {{ request.user.get_short_name }}</h1>
<p><strong>Persona:</strong> {{ profile.persona.name|default:"—" }}</p>
<p><strong>Interests:</strong>
  {% for ui in interests %}<span class="chip sel">{{ ui.interest.name }}</span>{% endfor %}
</p>
<p><a class="btn" href="{% url 'onboarding_persona' %}">Edit preferences</a>
   <a class="btn" href="{% url 'account_logout' %}">Sign out</a></p>
{% endblock %}
```

**Test Step 5:** register a fresh user → you're forced to `/onboarding/persona/` → pick a persona → pick interests → land on the dashboard showing your selections. Log out, log back in → you go straight to the dashboard (gate skipped).

## Step 6 — OAuth providers (Google + GitHub; Microsoft optional)

**Why:** Social login. allauth already has the routes; you only supply credentials + register the app once. (Provider setup steps are in Phase 6.)

There is **no new code** — the providers are already in `INSTALLED_APPS` and `SOCIALACCOUNT_PROVIDERS`. After creating OAuth apps (Phase 6) and filling the `.env` values:

```bash
python manage.py migrate          # ensures django.contrib.sites row exists
```
Set the Site in admin (`/admin/sites/site/`): domain `localhost:8000` (dev) or your real domain (prod).

**Test Step 6:** the "Google"/"GitHub" buttons on the login page complete a real OAuth round-trip, create a `User` + `UserProfile` (via the signal), and drop the user into onboarding.

## Step 7 — Pipeline bridge as a Django management command (optional, future-facing)

**Why:** So the existing pipeline can later read user preferences through Django ORM while keeping all its SQLAlchemy code. This does not change current behavior — it just gives you a Django-aware entry point.

`accounts/management/__init__.py`, `accounts/management/commands/__init__.py` — empty files.

`accounts/management/commands/run_digest.py`
```python
# accounts/management/commands/run_digest.py
"""
Bridge command: runs the existing pipeline from within Django so future
personalization can read user personas/interests via the Django ORM.

Today it simply delegates to the unchanged run_pipeline.main(), so behavior
is identical to `python run_pipeline.py`.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the AI news digest pipeline (Django-aware entry point)."

    def handle(self, *args, **options):
        import run_pipeline           # the existing, unchanged module
        run_pipeline.main()
        self.stdout.write(self.style.SUCCESS("Pipeline finished."))
```

**Test Step 7:** `python manage.py run_digest --help`-style behavior; running it executes the same three phases as before.

---

# Phase 5 — Integration With the Existing System

## 5.1 What existing files change — and what does NOT

**Nothing in `app/` needs to change to ship this feature.** The user system is purely additive. Here is the honest list:

| File | Change now? | Why |
|------|-------------|-----|
| `app/` (all scrapers, agents, services, models, repositories) | **No change** | The web layer is additive; the pipeline keeps running single-user. |
| `run_pipeline.py` | **No change now** | Still the working entry point. Optionally invoked via the Step 7 command. |
| `pyproject.toml` | Optional | You may add the web deps here, but I kept them in `requirements-web.txt` to avoid disturbing the pipeline's locked graph. |
| `.env` | **Add keys** | New `DJANGO_*` and OAuth vars (Step 0). Existing pipeline keys are reused. |
| `.gitignore` | **Add `staticfiles/`** | Don't commit collected static. |
| `create_tables.py` | **No change** | Still owns the content tables; runs independently of Django migrations. |

This satisfies your "don't break current functionality" constraint literally: the diff to the pipeline is **zero**.

## 5.2 How the digest pipeline will eventually use user preferences

This is the future work (explicitly out of scope now), but here is the exact, low-risk integration path the schema was designed for:

```mermaid
sequenceDiagram
    participant Cron as Scheduler
    participant Cmd as run_digest (mgmt cmd)
    participant DJ as Django ORM (users)
    participant Cur as CuratorAgent
    participant SA as SQLAlchemy (content)

    Cron->>Cmd: nightly trigger
    Cmd->>DJ: for each active user → persona + weighted interests
    Cmd->>SA: fetch recent articles/videos (unchanged)
    loop per user
        Cmd->>Cur: rank(content, persona, weighted_interests)
        Cur-->>Cmd: personalized top-N
    end
    Cmd->>SA: (unchanged) summaries already cached
    Cmd-->>Cron: per-user emails sent
```

Concretely, the only code that changes later is the **curator prompt builder**. Today `_build_system_prompt(profile)` (in `app/agents/curator_agent.py`) reads the static `config.UserProfile`. The future version accepts a small DTO populated from Django:

```python
# future: a thin adapter, no ORM coupling leaks into the agent
@dataclass
class RankingProfile:
    name: str
    persona: str                 # from UserProfile.persona.name
    weighted_interests: list[tuple[str, float]]   # from UserInterest
```

Because interests already carry `weight` and personas are a table you can attach ranking hints to, **the database never has to change** — only the prompt assembly. That is the dividend of the Phase 2 design.

## 5.3 Migration safety strategy (how to not break anything)

1. **Additive-only migrations.** Django only creates new tables; it never alters `articles`/`youtube_videos`.
2. **Separate migration tools.** Django migrations vs `create_tables.py` operate on disjoint table sets — they can run in any order.
3. **Feature-flag the personalization** when you build it: keep `config.UserProfile` as the default path; only switch to per-user ranking when a user has `onboarding_completed = True`. Single-user mode keeps working for anyone (including you) who hasn't onboarded.
4. **Backfill path:** when you go multi-user, create a `User` for yourself, onboard once, and the pipeline can transparently switch you from the `config.py` profile to your DB profile.
5. **Roll back cleanly:** `python manage.py migrate onboarding zero` and `migrate accounts zero` drop only the new tables; the content tables are untouched.

---

# Phase 6 — Deployment Plan (free / very low cost)

## 6.1 The recommended free stack (opinionated pick)

| Concern | Recommended | Why this one |
|---------|-------------|--------------|
| **Web hosting** | **Render** (free Web Service) | Native Python/Django, easy `build.sh` + `gunicorn`, free TLS, GitHub auto-deploy. Free tier sleeps on idle — fine for a grad demo. |
| **Database** | **Neon** (free Postgres) | Persistent (no 90-day expiry), generous free tier, plain `DATABASE_URL`, serverless autoscale-to-zero. Shared by web + pipeline. |
| **Pipeline scheduling** | **GitHub Actions cron** | Free 2,000 min/month, first-class Playwright/Chromium support, secrets vault, lives in your repo. |
| **Static files** | **WhiteNoise** | No separate CDN/bucket; Django serves compressed static itself. Zero cost, zero extra service. |
| **Email** | **Gmail SMTP** (already have it) | Reuse existing App Password; no new vendor. |
| **OAuth** | **Google + GitHub** now, Microsoft later | Fastest setup, widest coverage (see R1). |

```mermaid
flowchart TB
    Dev[GitHub repo] -->|push| Render[Render Web Service<br/>Django + gunicorn + WhiteNoise]
    Dev -->|cron schedule| GHA[GitHub Actions<br/>run pipeline nightly]
    Render --> Neon[(Neon PostgreSQL<br/>free, persistent)]
    GHA --> Neon
    Render -. OAuth .-> Providers[Google / GitHub]
    GHA -. SMTP .-> Gmail[Gmail]
    Users[Users] -->|HTTPS| Render
```

## 6.2 Why not the alternatives (so you can defend the choice)

- **Render free Postgres** — rejected: expires after 90 days; bad for a project you'll demo later. Neon is persistent.
- **Railway** — good DX, but the free credit is small and runs out; becomes paid quickly. Render's free web tier doesn't.
- **Fly.io** — powerful but requires a card and more ops knowledge; overkill here.
- **Heroku** — no meaningful free tier anymore.
- **PythonAnywhere** — easy, but its scheduled-task + Playwright story is weak; awkward for your Chromium pipeline.
- **Supabase** — excellent Postgres *and* its own auth; but using Supabase Auth would mean *not* using Django/allauth and learning a second auth system. As a Django-centric grad project, allauth + Neon is cleaner. (Supabase Postgres alone is a fine alternative to Neon if you prefer.)
- **Running the pipeline on the web host** — rejected (R3): Chromium bloat + a batch job in a web process. GitHub Actions is purpose-built for scheduled jobs.

## 6.3 Web deployment files

`build.sh` (Render build command)
```bash
#!/usr/bin/env bash
set -o errexit
pip install -r requirements-web.txt
python manage.py collectstatic --no-input
python manage.py migrate
```

`render.yaml` (replaces the current empty file)
```yaml
services:
  - type: web
    name: ai-news-web
    runtime: python
    plan: free
    buildCommand: "./build.sh"
    startCommand: "gunicorn core.wsgi:application"
    envVars:
      - key: DJANGO_SECRET_KEY
        generateValue: true
      - key: DJANGO_DEBUG
        value: "False"
      - key: DJANGO_ALLOWED_HOSTS
        value: "ai-news-web.onrender.com"
      - key: DJANGO_CSRF_TRUSTED_ORIGINS
        value: "https://ai-news-web.onrender.com"
      - key: DJANGO_DB_SSL
        value: "True"
      - key: DATABASE_URL
        sync: false        # paste the Neon connection string in the dashboard
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: GITHUB_CLIENT_ID
        sync: false
      - key: GITHUB_CLIENT_SECRET
        sync: false
      - key: GMAIL_ADDRESS
        sync: false
      - key: GMAIL_APP_PASSWORD
        sync: false
```
Make `build.sh` executable: `chmod +x build.sh && git add build.sh`.

## 6.4 PostgreSQL (Neon) setup

1. Create a free Neon project → copy the connection string (`postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require`).
2. Put it in **both** places: Render env (`DATABASE_URL`) and the GitHub Actions secret.
3. Locally, you can keep using your Docker Postgres; set `DATABASE_URL` to Neon only when you want to test against prod data.
4. Run `migrate` once against Neon (Render's `build.sh` does this automatically on deploy).
5. Run the pipeline's `create_tables.py` against Neon once so the content tables exist there too:
   ```bash
   DATABASE_URL="<neon-url>" python -m app.database.create_tables
   ```

## 6.5 OAuth provider setup (exact steps)

**Google** (~10 min): Google Cloud Console → *APIs & Services → Credentials → Create OAuth client ID → Web application*.
- Authorized redirect URIs:
  - `http://localhost:8000/accounts/google/login/callback/`
  - `https://ai-news-web.onrender.com/accounts/google/login/callback/`
- Copy Client ID/secret → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.

**GitHub** (~5 min): GitHub → *Settings → Developer settings → OAuth Apps → New OAuth App*.
- Authorization callback URL: `https://ai-news-web.onrender.com/accounts/github/login/callback/` (add a localhost one too).
- Copy Client ID/secret → `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`.

**Microsoft** (optional, ~20 min): Azure Portal → *Microsoft Entra ID → App registrations → New registration*.
- Redirect URI (Web): `https://ai-news-web.onrender.com/accounts/microsoft/login/callback/`.
- Create a client secret → `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET`; set `MICROSOFT_TENANT=common` for personal + work accounts.

After deploy, set the **Site** domain in `/admin/sites/site/` to `ai-news-web.onrender.com`. (allauth's modern provider config via `SOCIALACCOUNT_PROVIDERS` means you do **not** also have to create SocialApp rows in admin — the `.env` credentials are used directly.)

## 6.6 Static files strategy

WhiteNoise + `collectstatic` (run in `build.sh`) + `CompressedManifestStaticFilesStorage`. This serves hashed, compressed assets straight from the web process. **No S3/CDN/bucket needed** — the right call for a low-traffic graduation project.

## 6.7 Scheduled pipeline execution (GitHub Actions)

`.github/workflows/pipeline.yml`
```yaml
name: nightly-digest
on:
  schedule:
    - cron: "0 6 * * *"     # 06:00 UTC daily
  workflow_dispatch: {}      # allow manual runs from the Actions tab

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"   # see note: pin a CI-supported version
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .            # installs the pipeline (pyproject.toml)
          python -m playwright install --with-deps chromium
      - name: Run digest pipeline
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          RECIPIENT_EMAIL: ${{ secrets.RECIPIENT_EMAIL }}
          RESIDENTIAL_PROXY_URL: ${{ secrets.RESIDENTIAL_PROXY_URL }}
        run: python run_pipeline.py
```
Add each value under *GitHub repo → Settings → Secrets and variables → Actions*.

> **Note / risk surfaced again (R6 earlier R-line was about Postgres; this is the 3.14 issue from the prior audit):** your `pyproject.toml` pins `requires-python = ">=3.14"`, but GitHub Actions and most hosts don't ship 3.14 yet. For deployment you'll want to relax that to `>=3.11` (the code uses nothing 3.14-specific). This is a one-line change you'll make when you tackle deployment — flagging it so the CI above actually runs.

---

# Final checklist (do them in this order)

```text
[ ] Step 0  pip install web deps; create core/, manage.py; python manage.py check
[ ] Step 1  custom User + AUTH_USER_MODEL; makemigrations accounts; migrate; createsuperuser
[ ] Step 2  profile signal; verify user.profile exists
[ ] Step 3  allauth templates; test signup/login/logout/reset locally
[ ] Step 4  onboarding models; makemigrations; data migration seeds 7 personas + 15 interests; migrate
[ ] Step 5  onboarding forms/views/urls/middleware/templates; test the gate end-to-end
[ ] Step 6  create Google + GitHub OAuth apps; fill .env; test social login
[ ] Step 7  (optional) run_digest management command
[ ] Deploy  Neon DB → Render web (render.yaml + build.sh) → GitHub Actions cron
[ ] Cleanup relax requires-python to >=3.11 for CI/hosting
```

## What I deliberately did NOT build (avoiding overengineering)

- No JWT/token auth (Django sessions are correct here).
- No DRF/REST API or SPA (server-rendered is enough).
- No personalization/ranking engine yet (schema is ready; logic is future work).
- No migration of the pipeline to Django ORM (zero-risk coexistence instead).
- No Celery/Redis broker for scheduling (GitHub Actions cron is simpler and free).
- No separate static host (WhiteNoise covers it).

---

*This is a design + implementation blueprint. No existing code was modified and no new files were written to your project yet — when you're ready, say the word and I'll start creating the actual files (Step 0 onward) directly in the repo, one step at a time so each is testable before moving on.*
