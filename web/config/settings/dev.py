"""Local development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# M15 — the frontend/ dev server (next dev, localhost:3000) proxies to this
# runserver via next.config.ts's rewrites(), which is a server-to-server
# request: Django sees Host=127.0.0.1:8000 but the browser's real Origin
# header still says http://localhost:3000, so Django 4+'s Origin-vs-Host
# CSRF check fails with "Origin checking failed" on every POST from the new
# frontend (confirmed live) unless localhost:3000 is explicitly trusted.
# Dev-only: production's single Caddy domain never has this Origin/Host
# split, so prod.py's own CSRF_TRUSTED_ORIGINS (env-driven) is untouched.
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]

# EMAIL_BACKEND is set in base.py — real Gmail SMTP if GMAIL_ADDRESS/
# GMAIL_APP_PASSWORD are configured in web/.env, console (prints instead of
# sending) otherwise. Not overridden here so a real dev environment with
# real credentials actually delivers mail.
