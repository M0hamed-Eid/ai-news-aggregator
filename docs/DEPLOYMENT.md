# Production Deployment Guide

This is the deployment guide for taking the local dev setup (Docker-based
Postgres+Redis, Django `web/`, the SQLAlchemy pipeline `app/`, Next.js
`frontend/`) to a real, reachable production deployment with zero data loss.

> **Current status (2026-08-09): the frontend deploys to Vercel; the
> backend is moving to AWS EC2.** Oracle Cloud's "Always Free" tier had no
> ARM capacity available when provisioned (a documented, common risk — see
> Known Limitations), so the backend host changed from the originally
> planned Oracle VM to an AWS EC2 instance, paid for out of a time-boxed
> AWS credit rather than staying strictly $0/month. This is a **split-host,
> cross-origin** architecture now, not the original single-VM/single-domain
> design: Vercel serves the whole Next.js app shell on its own domain, and
> the EC2 instance runs Django/Celery as an **API-only** backend on a
> separate domain, reached cross-origin (see `web/config/settings/prod.py`'s
> `CORS_ALLOWED_ORIGINS` / `SESSION_COOKIE_SAMESITE="None"`, and
> `frontend/src/lib/api.ts`'s `NEXT_PUBLIC_API_BASE_URL`). The `frontend`
> service that used to live in `docker-compose.prod.yml` (and
> `frontend/Dockerfile`) is stale/unused as a result — see Section 3c.
>
> The database migration steps in Section 4 below predate this session's
> actual production data migration, which instead went through a series of
> dedicated, tested GitHub Actions workflows
> (`.github/workflows/neon-content-sync.yml`,
> `neon-django-migrate.yml`, `neon-add-user29.yml`,
> `neon-delete-stale-accounts.yml`) built specifically to work around this
> dev machine's inability to reach Neon's Postgres port directly — each is
> idempotent (`ON CONFLICT DO NOTHING` / natural-key remapping) and safe to
> re-run. Section 4's `scripts/*.ps1` approach is still valid for a
> from-scratch migration; it just isn't what actually happened here.

Three paths are documented:

- **AWS EC2 + Docker Compose (current backend path).** Same Docker Compose
  stack as the Oracle path below — Oracle's docker-compose.prod.yml file
  doesn't care which cloud VM it runs on — just provisioned on AWS instead,
  paired with the frontend on Vercel instead of a `frontend` container. See
  Section 3c.
- **Oracle Cloud "Always Free" VM + Docker Compose (original primary,
  blocked on capacity).** Runs this project's full multi-process model
  (Django, all 3 Celery workers, beat, Redis, and originally the frontend
  too) persistently and unmodified on a single VM/domain — the closest
  possible match to local dev, and the only path that keeps semantic search
  and "add a source" exactly as synchronous as they are locally. Revisit if
  Oracle capacity frees up later.
- **Fallback: Render free web service + GitHub Actions.** Django only, no
  background workers (pipeline runs via GitHub Actions instead). Use if
  neither AWS nor Oracle is workable.

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

**AWS EC2 path additionally needs:**
- An AWS account with billing set up (this path is not free-tier — budget
  against whatever credit/card is on the account; a `t3.small` running this
  full stack costs roughly $15-20/month on-demand, well inside a $100
  credit for a several-week deployment window).
- An EC2 instance: **Ubuntu 22.04/24.04 LTS, `t3.small` (2GB RAM) minimum**
  — `t3.micro`'s 1GB will OOM building multiple Docker images back-to-back
  (worker/beat/web/chat all share the root `Dockerfile`, `web/Dockerfile`
  separately) plus running redis + 5 Celery-adjacent processes at once. In
  the EC2 launch wizard: enable "Auto-assign public IP", create/download a
  new SSH key pair (`.pem`), and open these inbound rules in its security
  group: **22 (SSH, ideally restricted to your own IP)**, **80 (HTTP, for
  Let's Encrypt's challenge)**, **443 (HTTPS)**.
- Docker + the Compose plugin installed on that instance (same as Oracle —
  `curl -fsSL https://get.docker.com | sh` then `sudo usermod -aG docker
  $USER` and re-login covers Ubuntu).
- A domain name pointed at the instance's public IP (an A record), or a
  free dynamic-DNS hostname (e.g. duckdns.org) — same Let's-Encrypt-needs-
  public-DNS constraint as the Oracle path below. **This backend domain is
  separate from the Vercel frontend domain** — e.g. `api.yourapp.com` (or
  `yourapp.duckdns.org`) for the backend, `yourapp.vercel.app` (or a custom
  domain attached in Vercel) for the frontend.
- A Vercel account with `frontend/` connected as its own project (Root
  Directory setting = `frontend` if the repo root isn't the Next.js app —
  see Section 3c's Vercel note). `NEXT_PUBLIC_API_BASE_URL` set in Vercel's
  project env vars to `https://<your-backend-domain>`.

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

## 3c. Deploy steps — Current path (AWS EC2 backend + Vercel frontend)

Backend (EC2 — same Docker Compose stack the Oracle path uses, just a
different VM provider; steps 1-6 below are otherwise identical to Section
3's Oracle steps):

1. Provision the EC2 instance (see Prerequisites) and point your backend
   domain's DNS A record at its public IP — do this before step 5, or
   Caddy's Let's Encrypt challenge will fail.
2. SSH in: `ssh -i your-key.pem ubuntu@<instance-public-ip>`. Install
   Docker + the Compose plugin (`curl -fsSL https://get.docker.com | sh`,
   then `sudo usermod -aG docker $USER` and reconnect).
3. `git clone` this repository onto the instance.
4. Copy and fill in the three env files (`.env.prod`, `web/.env.prod`,
   `docker/.env` — set `SITE_DOMAIN` to your **backend** domain, e.g.
   `api.yourapp.com`, not the Vercel one). Critically, `web/.env.prod`'s
   `DJANGO_CORS_ALLOWED_ORIGINS` must include your actual Vercel URL
   (`https://yourapp.vercel.app` or your custom Vercel domain, full origin
   including scheme, comma-separated if there's more than one — e.g. a
   Vercel preview URL alongside the production one), and
   `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` must include the
   backend domain itself.
5. Run the database migration (Section 4) — do this before bringing the
   app up, so it starts with real data already in place. (This project's
   own Neon data was actually migrated via the GitHub Actions workflows
   noted in the status callout at the top of this doc, not this section's
   scripts — either approach reaches the same end state.)
6. `docker compose -f docker/docker-compose.prod.yml up -d --build` — this
   now builds/starts only the backend services (`redis`, `web`, `chat`,
   `worker-default`, `worker-interactive`, `worker-stt`, `beat`, `caddy`;
   no `frontend` container, see the status callout at the top of this doc).
   Watch `docker compose -f docker/docker-compose.prod.yml logs -f caddy`
   until it reports a successful certificate issuance, then visit
   `https://<your-backend-domain>/healthz/` — expect `{"status": "ok"}`.

Frontend (Vercel):

1. In Vercel: New Project → import this GitHub repo. Since the Next.js app
   lives in `frontend/`, not the repo root, set **Root Directory** to
   `frontend` in the project's General settings (this is almost certainly
   what caused the very first deploy attempt's `NOT_FOUND` error if it
   wasn't set — Vercel otherwise looks for a Next.js app at the repo root
   and finds nothing to serve).
2. Set the `NEXT_PUBLIC_API_BASE_URL` environment variable to
   `https://<your-backend-domain>` (the EC2/Caddy domain from above, not
   the Vercel domain itself) in the Vercel project's env var settings, then
   redeploy so the build picks it up (Next.js inlines `NEXT_PUBLIC_*` vars
   at build time, not runtime).
3. Push to `main` (or redeploy manually from the Vercel dashboard) — Vercel
   auto-builds and serves from `frontend/` going forward.
4. Visit the Vercel URL — the home page should render with real content
   (not a 404), and network requests to `/api/*` etc. should resolve to
   the backend domain, not 404 or CORS-error in the browser console.

---

## 4. Database migration (zero data loss)

**Use Neon's DIRECT connection string, not the pooled one, for
restore/migration.** Neon's dashboard shows a "Connection pooling" toggle —
turn it OFF to get the direct string (hostname has no `-pooler` segment).
Confirmed live: running `pg_restore` against the *pooled* connection string
reports success (exit 0) but silently creates zero tables — Neon's pooler
runs in PgBouncer transaction mode, which doesn't reliably support the kind
of multi-statement session `pg_restore` needs. The pooled string is fine for
the running app's normal query traffic; it is NOT fine for `pg_dump`/
`pg_restore`.

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

### If your network blocks outbound port 5432

Some networks (corporate/managed machines especially) block outbound
Postgres (5432) entirely while allowing normal HTTPS through — confirmed
live on this project's own dev machine (times out from both Docker and a
direct Python connection; even tunneling through Docker Desktop's own HTTP
proxy failed, since that proxy only allows CONNECT to port 443). If
`restore_db.ps1`/`verify_migration.ps1` hang or refuse to connect, don't
assume Neon or the scripts are broken — check this first (`Test-NetConnection
<neon-host> -Port 5432` from PowerShell, or the raw TCP test in
`scripts/verify_migration.ps1`'s troubleshooting notes).

Workaround that doesn't depend on fixing the local network: GitHub-hosted
Actions runners have normal, unrestricted outbound access, so they can reach
Neon directly. Push the export to a throwaway branch and let a workflow do
the restore there instead:

1. Add a `NEON_DATABASE_URL` repo secret (Settings → Secrets and variables →
   Actions) — the DIRECT connection string, not pooled.
2. `git checkout -b db-migration-temp && git add -f ai_news_export.dump .github/workflows/migrate-db-once.yml && git commit -m "..." && git push -u origin db-migration-temp`
   (the dump is normally gitignored — `-f` overrides that for this one
   throwaway commit only).
3. The push triggers `.github/workflows/migrate-db-once.yml` automatically —
   watch it in the Actions tab; its last step prints row counts for every
   table plus total DB size, the same proof `verify_migration.ps1` gives
   locally.
4. Once confirmed, delete the throwaway branch (`git push origin --delete
   db-migration-temp && git branch -D db-migration-temp`) so the dump
   doesn't linger in git history longer than necessary.

This was actually how this project's own production data was migrated —
confirmed live: 3,444 articles / 123 videos / 3,567 embeddings / 3,480
enrichment rows / 8 users / 4,793 events, all matching.

### Database restore (disaster recovery)

If you ever need to restore from a fresh `export_db.ps1` dump against an
empty database (e.g. rebuilding after a lost Neon project), the same
`restore_db.ps1` command works unchanged — it's idempotent enough for a
fresh target (`CREATE EXTENSION IF NOT EXISTS` + `pg_restore --clean
--if-exists`).

---

## 5. Redeploy after updates

**AWS EC2 / Oracle path (same mechanism, cloud-agnostic):** push to `main`;
`.github/workflows/deploy.yml` SSHes into the instance and runs `git pull &&
docker compose -f docker/docker-compose.prod.yml up -d --build` automatically
once CI passes — set its `DEPLOY_HOST`/`DEPLOY_USER`/`DEPLOY_SSH_KEY` repo
secrets to point at whichever instance you're actually running (EC2's public
IP + `ubuntu` user + the `.pem` key's contents, for AWS). To do it manually:
```
ssh <user>@<instance-host> "cd ai-news-aggregator && git pull && docker compose -f docker/docker-compose.prod.yml up -d --build"
```

**Vercel (frontend):** push to `main` — Vercel's own native auto-deploy
picks it up once the project is connected; no extra step.

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

Domain: **`aicompass.duckdns.org`** (free DDNS, already registered — currently
points at whatever IP was set when it was created; **must be updated to the
Oracle VM's real public IP once it's provisioned**, via
https://www.duckdns.org/domains before the first deploy, or Caddy's Let's
Encrypt challenge will fail).

| Endpoint | Path | Notes |
|---|---|---|
| Home | `https://aicompass.duckdns.org/` | Public |
| Feed | `https://aicompass.duckdns.org/feed/` | Authenticated |
| Search | `https://aicompass.duckdns.org/search/` | Public, degrades to keyword search if the interactive worker is briefly down |
| Admin | `https://aicompass.duckdns.org/admin/` | Staff only |
| Ops dashboard | `https://aicompass.duckdns.org/ops/` | Staff only |
| Health check | `https://aicompass.duckdns.org/healthz/` | `{"status": "ok"}` / 503 |
| Digest click redirect | `https://aicompass.duckdns.org/r/<token>/` | Used only inside sent digest emails |
| Stripe webhook | `https://aicompass.duckdns.org/accounts/stripe/webhook/` | Configure this exact URL in the Stripe dashboard |
| API | N/A | Public REST API is out of scope (deferred per `docs/ROADMAP.md`, same as M13) |

Postgres: Neon project created (`neondb`, AWS us-east-1) — connection string
lives in `.env.prod`/`web/.env.prod` (gitignored, not in this doc). **Migrated
and verified**: this dev machine's network blocks outbound port 5432 to
Neon (confirmed from both Docker and a direct Python connection), so the
migration ran via the GitHub Actions workaround documented in Section 4
instead. Verified row counts: 3,444 articles / 123 videos / 3,567
embeddings / 3,480 enrichment rows / 8 users / 4,793 events — 37MB total.

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
