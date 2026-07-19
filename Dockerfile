# Pipeline image — scrape/embed/enrich/cluster/score/digest/STT + all 3
# Celery worker processes + beat. Reused unmodified by every worker/beat
# service in docker/docker-compose.prod.yml; only the container `command:`
# differs, matching the 4 process invocations already documented in
# README.md ("Run the worker + beat", "dedicated interactive worker",
# "dedicated stt worker").
#
# Python 3.14 (matches pyproject.toml's requires-python) — deliberately a
# DIFFERENT base image from web/Dockerfile's 3.13 (Django 5.2 officially
# targets <=3.13; see .wolf/cerebrum.md's 2026-06-24 note). Keeping the two
# images on their own Python versions preserves the project's existing
# two-independent-environments convention instead of forcing one runtime
# to fit both.

FROM python:3.14-slim

# ffmpeg: faster-whisper/yt-dlp audio extraction (M12 STT).
# Chromium's own apt deps are installed separately below via `playwright
# install --with-deps`, which knows the exact package list for its bundled
# browser build — duplicating that list here would drift out of sync.
#
# HTTPS, not the base image's default plain-HTTP apt sources — some
# container-network setups (corporate/sandboxed Docker Desktop proxies)
# block or 403 plain HTTP to deb.debian.org while allowing HTTPS through
# unchanged; switching is strictly safer either way.
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/*.sources 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# uv, copied from the official distroless image rather than `pip install uv`
# — matches how this project already manages the root environment (uv.lock
# exists; README's Step 0 uses `uv sync`, never `pip install -e .`).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first (cache layer) — installed into the system interpreter,
# not a venv; there is no reason to double up virtualization inside an
# already-isolated container.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Playwright's headless Chromium (app/scrapers/blog_scraper.py — the
# BlogScraper for blog_openai/blog_anthropic). --with-deps pulls exactly the
# system libraries that build needs, not a hand-maintained apt list.
RUN uv run playwright install --with-deps chromium

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Default: the main worker (default queue — scrape/stt-dispatch/embed/
# enrich/deep-video/cluster/score/digest/affinity/ranking). docker-compose
# overrides `command:` for worker-interactive, worker-stt, and beat.
CMD ["uv", "run", "celery", "-A", "app.celery_app:celery_app", "worker", "--pool=solo", "--loglevel=info"]
