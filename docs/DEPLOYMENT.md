# Production Deployment Guide

This is the deployment guide for taking the local dev setup (Docker-based
Postgres+Redis, Django `web/`, the SQLAlchemy pipeline `app/`) to a real,
reachable, $0/month production deployment with zero data loss.

Two paths are documented:

- **Primary: Oracle Cloud "Always Free" VM + Docker Compose.** Runs this
  project's full multi-process model (Django, all 3 Celery workers, beat,
  Redis) persistently and unmodified — the closest possible match to local
  dev, and the only path that keeps semantic search and "add a source"
  exactly as synchronous as they are locally.
- **Fallback: Render free web service + GitHub Actions.** Use this if Oracle
  provisioning proves impractical (see Known Limitations). No source code
  changes either way — the fallback documents a real, disclosed limitation
  instead of redesigning product behavior.

Read the architecture rationale in full before deploying: see the approved
plan this guide implements, summarized in the Known Limitations section
below and in `.wolf/cerebrum.md`'s 2026-07-19 decision-log entry.

---

## 1. Prerequisites

**Both paths need:**
- A [Neon](https://neon.tech) account and a free project (Postgres 16+,
  pgvector-capable — every Neon plan supports it). Note the connection
  string; you'll use it twice (once as `postgresql+psycopg2://...` for the
  pipeline, once as `postgres://...` for Django — same host/credentials,
  different URL scheme, exactly like this project's local `.env` /
  `web/.env` already do).
- A GitHub repository this project is pushed to (for CI, and for the
  Oracle path's SSH-pull-based redeploy).
- Real credentials for: Groq (`GROQ_API_KEY`), Gmail App Password
  (`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` — same as local dev), and, if
  billing is wanted live, Stripe test-mode keys.

**Primary (Oracle) path additionally needs:**
- An [Oracle Cloud](https://www.oracle.com/cloud/free/) account. Signup
  requires a valid credit card for identity verification — Oracle's own
  terms say Always-Free resources are never billed unless you explicitly
  upgrade to Pay-As-You-Go, but budget for the friction of providing one.
- A provisioned "Always Free" Ampere A1 VM (2 OCPU / 12GB RAM under the
  current, 2026-reduced allocation). **Known friction:** Oracle's ARM
  capacity is well-documented as hard to obtain on demand — "out of host
  capacity" errors are common and can take retries over hours to days to
  clear, especially in busy regions. If your home region has multiple
  availability domains, try each one; otherwise keep retrying, or fall back
  to the Render path below while you wait.
- Docker + Docker Compose installed on that VM.
- A domain name pointed at the VM's public IP, OR a free dynamic-DNS
  hostname (e.g. [duckdns.org](https://www.duckdns.org)) if you don't have
  one — either way, it must resolve publicly before the first
  `docker compose up`, or Caddy's Let's Encrypt challenge will fail.

**Fallback (Render) path additionally needs:**
- A [Render](https://render.com) account (no card required for the free
  tier).
- An [Upstash](https://upstash.com) account for free managed Redis (no card
  required).

---

## 2. Environment variables

Two separate env files, exactly mirroring this project's existing local
convention (root `.env` for the pipeline, `web/.env` for Django — same
Postgres, different URL scheme per process):

| File | Consumed by | Key vars |
|---|---|---|
| `.env.prod` (repo root, gitignored) | `worker-default`, `worker-interactive`, `worker-stt`, `beat` | `DATABASE_URL` (`postgresql+psycopg2://...`), `REDIS_URL`, `GROQ_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `WHISPER_MODEL`, `LLM_PROVIDER`, `HOURS_LOOKBACK`, `LOG_LEVEL`, `DJANGO_BASE_URL` |
| `web/.env.prod` (gitignored) | `web` | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (`postgres://...`), `REDIS_URL`, `CELERY_BROKER_URL`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_PRO` |
| `docker/.env` (gitignored, Oracle path only) | `docker-compose.prod.yml` itself (Caddy) | `SITE_DOMAIN` |

Base every value on this repo's existing `.env.example` / `web/.env.example`
/ `docker/.env.prod.example` files — copy each, fill in real values, never
commit the copy.

**On the Oracle path**, since Redis is self-hosted on the same VM (not a
managed single-DB service), `REDIS_URL`/`CELERY_BROKER_URL` work exactly
like local dev — point them at `redis://redis:6379/1` and
`redis://redis:6379/0` respectively (hostname `redis` resolves via Docker
Compose's network, same DB-index split as local).

**On the Render fallback path**, use two separate free Upstash Redis
databases (Upstash's managed Redis doesn't reliably support multi-DB
`SELECT`) — one for `REDIS_URL`, one for `CELERY_BROKER_URL`.

---

## 3. Deploy steps — Primary (Oracle Cloud VM + Docker Compose)

1. Provision the VM (see Prerequisites) and SSH in. Install Docker + the
   Compose plugin.
2. `git clone` this repository onto the VM.
3. Copy and fill in the three env files above (`.env.prod`,
   `web/.env.prod`, `docker/.env`).
4. Run the database migration first (see Section 4) — do this BEFORE
   bringing the app up, so it starts with real data already in place.
5. From the repo root:
   ```
   docker compose -f docker/docker-compose.prod.yml up -d --build
   ```
   This builds both images (root `Dockerfile` for the pipeline/worker/beat
   image, `web/Dockerfile` for Django) and starts all 6 services: `redis`,
   `web`, `worker-default`, `worker-interactive`, `worker-stt`, `beat`,
   `caddy`.
6. Watch logs until Caddy reports a successful certificate issuance:
   ```
   docker compose -f docker/docker-compose.prod.yml logs -f caddy
   ```
7. Visit `https://<your domain>/healthz/` — expect `{"status": "ok"}`.

## 3b. Deploy steps — Fallback (Render + GitHub Actions)

1. Create the free Neon project and two free Upstash Redis databases (see
   Prerequisites).
2. In Render: New → Blueprint, point at this repo — it reads the root
   `render.yaml` (Docker-based, builds `web/Dockerfile`). Fill in the
   `sync: false` env vars in the Render dashboard when prompted.
3. Run the database migration (Section 4).
4. Render auto-deploys on push to `main` once connected — no extra step.
5. Set up `.github/workflows/pipeline.yml`'s repo secrets (`DATABASE_URL`,
   `REDIS_URL`, `GROQ_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`) so
   the scheduled pipeline runs (see `.github/workflows/`).
6. Visit `https://<your-app>.onrender.com/healthz/` — expect
   `{"status": "ok"}`.

---

## 4. Database migration (zero data loss)

Run these from the repo root, on your LOCAL machine (they use Docker to
reach both the local dev container and the remote Neon database — no local
Postgres client install needed):

```powershell
# 1. Export the local dev database
.\scripts\export_db.ps1

# 2. Restore it into Neon (creates the pgvector extension first)
.\scripts\restore_db.ps1 -NeonConnectionString "postgresql://user:pass@ep-xxx.neon.tech/ai_news?sslmode=require"

# 3. Verify every table/record actually migrated — a real row-count diff,
#    not a visual spot-check
.\scripts\verify_migration.ps1 -NeonConnectionString "postgresql://user:pass@ep-xxx.neon.tech/ai_news?sslmode=require"
```

`verify_migration.ps1` exits non-zero if any table's row count doesn't
match between local and Neon — do not proceed to cutover until it passes
clean.

### Database restore (disaster recovery)

If you ever need to restore from a fresh `export_db.ps1` dump against an
empty database (e.g. rebuilding after a lost Neon project), the same
`restore_db.ps1` command works unchanged — it's idempotent enough for a
fresh target (`CREATE EXTENSION IF NOT EXISTS` + `pg_restore --clean
--if-exists`).

---

## 5. Redeploy after updates

**Oracle path:** push to `main`; `.github/workflows/deploy.yml` SSHes into
the VM and runs `git pull && docker compose -f docker/docker-compose.prod.yml
up -d --build` automatically once CI passes. To do it manually:
```
ssh <user>@<vm-host> "cd ai-news-aggregator && git pull && docker compose -f docker/docker-compose.prod.yml up -d --build"
```

**Render fallback path:** push to `main` — Render's own native auto-deploy
picks it up; no extra step.

Django migrations run automatically on every `web` container start
(`web/Dockerfile`'s `CMD`) — safe, since they only ever touch Django-owned
tables (users, auth_*, onboarding, accounts, behavior).

---

## 6. Rollback procedure

**Oracle path:**
```
ssh <user>@<vm-host> "cd ai-news-aggregator && git checkout <previous-tag-or-commit> && docker compose -f docker/docker-compose.prod.yml up -d --build"
```
If a bad deploy included a Django migration you need to undo: `docker
compose -f docker/docker-compose.prod.yml exec web python manage.py migrate
<app> <previous_migration_name>` before checking out the old code, then
redeploy.

If the DATABASE itself needs restoring (not just the app code) — re-run
`.\scripts\restore_db.ps1` against a prior `export_db.ps1` dump. Neon also
keeps its own point-in-time-restore window (check your plan's retention) as
a second line of defense, independent of this project's own scripts.

**Render fallback path:** Render's dashboard has a one-click "redeploy a
previous version" per-service — no manual git steps needed.

---

## 7. Production URLs

Fill in once actually deployed (this cannot be done before a real domain/
Render URL exists):

| Endpoint | Path | Notes |
|---|---|---|
| Home | `/` | Public |
| Feed | `/feed/` | Authenticated |
| Search | `/search/` | Public, degrades to keyword search if the interactive worker is briefly down |
| Admin | `/admin/` | Staff only |
| Ops dashboard | `/ops/` | Staff only |
| Health check | `/healthz/` | `{"status": "ok"}` / 503 |
| Digest click redirect | `/r/<token>/` | Used only inside sent digest emails |
| Stripe webhook | `/accounts/stripe/webhook/` | Configure this exact URL in the Stripe dashboard |
| API | N/A | Public REST API is out of scope (deferred per `docs/ROADMAP.md`, same as M13) |

---

## 8. Validation checklist

After deploying, verify each of these against the real production URL:

- [ ] User registration → verification email received → account verified
- [ ] Login → "Forgot password?" → reset email → new password works
- [ ] Source submission → live synchronous verdict (Oracle path) or the
      documented graceful-degradation message (fallback path)
- [ ] News ingestion — confirm Celery beat (Oracle) or the GitHub Actions
      `pipeline.yml` run (fallback) actually inserted new rows
- [ ] Semantic search returns real semantic results (Oracle path) or falls
      back to keyword search with the visible banner (fallback path)
- [ ] Recommendations / `/feed/` shows a real, personalized ranking
- [ ] Admin panel reachable, staff-only
- [ ] `/ops/` dashboard reachable, shows real source health
- [ ] `/healthz/` returns 200

---

## 9. Known limitations (disclosed, not hidden)

- **Oracle ARM capacity risk.** Provisioning the free VM can fail with "out
  of host capacity" and may take retries over hours to days. Oracle also
  cut the Always-Free ARM allocation once already in 2026 (4 OCPU/24GB →
  2 OCPU/12GB for free-tier accounts) — a real policy-durability risk beyond
  the provisioning friction itself.
- **STT (faster-whisper) runs from a datacenter IP either way.** This
  project's own pre-existing design note says the STT worker "should run
  from a residential-IP host" (yt-dlp anti-bot risk) — neither the Oracle
  VM nor Render is a residential IP. Not solved by this deployment; jobs
  queue on the `stt` queue and may fail/get rate-limited depending on
  YouTube's current blocking behavior. Videos without captions still flow
  through enrichment without a transcript (the existing, tolerant fallback).
- **Fallback path only:** semantic search and "add a source" lose their
  live synchronous verdict — search falls back to keyword search (a real,
  already-built, tested fallback), and source submission will return "could
  not validate right now" every time, since no free host in this path runs
  a persistent interactive-queue worker. Two ways to recover full parity
  without redesigning the product: (a) switch to the Oracle path, or (b) run
  the interactive worker yourself, anywhere with steady internet, pointed
  at the production Redis/Postgres:
  ```
  python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h
  ```
  This is optional and off by default — it's your own machine standing in
  for the free tier's missing second process, exactly as you could already
  do against your local dev stack.
- **Cold-start on first deploy/restart (Oracle path) — mitigated, not
  eliminated.** The embedding model (sentence-transformers) is pre-loaded at
  worker startup (`app/celery_app.py`'s `worker_process_init` handler) so the
  very first live search/source-submission request doesn't itself pay the
  load cost — confirmed live at 1.57s end-to-end on a freshly-restarted
  worker. This still depends on `docker-compose.prod.yml`'s `hf_cache`
  volume persisting the downloaded model across restarts; if that volume is
  ever wiped (`docker compose down -v`), the NEXT container start will spend
  roughly a minute downloading the model again during its own startup
  (before accepting any task, so it still won't time out a real user's
  request — it just delays that one container becoming ready).
