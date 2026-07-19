# Django web image — deliberately separate from the root Dockerfile (the
# pipeline/worker/beat image). Kept on Python 3.13 (Django 5.2 officially
# targets <=3.13, per .wolf/cerebrum.md's 2026-06-24 note — the pipeline's
# own Dockerfile is 3.14) and installs only web/requirements.txt — none of
# the pipeline's ML/scraping stack (sentence-transformers, faster-whisper,
# playwright) belongs in this image; Django never imports any of it.

FROM python:3.13-slim

# HTTPS, not the base image's default plain-HTTP apt sources -- some
# container-network setups (corporate/sandboxed Docker Desktop proxies)
# block or 403 plain HTTP to deb.debian.org while allowing HTTPS through
# unchanged; switching is strictly safer either way.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/*.sources 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

EXPOSE 8000

# Migrations only ever touch Django-owned tables (users, auth_*, onboarding,
# accounts, behavior — see the module docstrings throughout web/apps/*/models.py
# for the "each ORM owns only its own tables" convention) — safe to run on
# every container start, same as any single-service Django deploy.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile -"]
