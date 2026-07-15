# AI News Aggregator — Backend Setup Guide

Complete guide to spinning up the database, running the pipeline, and
verifying everything works end to end.

---

## Project Layout

```
ai-news-aggregator/
├── app/
│   ├── config.py                        # Channel list, scraper settings
│   ├── scrapers/
│   │   ├── base_scraper.py              # ScrapedArticle dataclass + BaseScraper
│   │   ├── youtube_scraper.py
│   │   └── blog_scraper.py
│   ├── database/
│   │   ├── __init__.py                  # Public API: get_db_session, models, repos
│   │   ├── base.py                      # SQLAlchemy DeclarativeBase
│   │   ├── session.py                   # Engine + SessionLocal + get_db_session()
│   │   ├── create_tables.py             # One-time table initialisation script
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── article.py               # OpenAI + Anthropic blog posts
│   │   │   └── youtube_video.py         # YouTube transcripts
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── base_repository.py       # Generic CRUD (get_by_id, delete, count)
│   │       ├── article_repository.py    # Article-specific queries + bulk insert
│   │       └── youtube_repository.py    # Video-specific queries + bulk insert
│   ├── agents/                          # (Phase 2 — curator, digest, email)
│   └── services/                        # (Phase 2 — scheduler, email sender)
├── docker/
│   └── docker-compose.yml               # PostgreSQL + pgAdmin
├── tests/
│   ├── test_scrapers.py
│   ├── test_blog_scraper.py
│   └── test_database.py                 # Repository + model + session tests
├── run_pipeline.py                      # Main entry point
├── .env.example
└── pyproject.toml
```

---

## Phase 1 — Environment Setup

### 1. Copy and fill the environment file

```bash
cp .env.example .env
```

Edit `.env`:
```
POSTGRES_DB=ai_news
POSTGRES_USER=ai_news_user
POSTGRES_PASSWORD=your_strong_password_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg2://ai_news_user:your_strong_password_here@localhost:5432/ai_news
OPENAI_API_KEY=sk-...
```

### 2. Install Python dependencies

```bash
uv sync
# or
pip install -r requirements.txt
```

---

## Phase 2 — Start PostgreSQL

```bash
# Start in the background
docker compose -f docker/docker-compose.yml up -d

# Verify it's healthy
docker compose -f docker/docker-compose.yml ps
# You should see:  ai_news_db ... (healthy)

# View logs if something goes wrong
docker compose -f docker/docker-compose.yml logs db
```

**pgAdmin** (optional browser UI) is at: http://localhost:5050  
Login: `admin@local.dev` / `admin`

To add a server in pgAdmin:
- Name: `ai_news_local`
- Host: `db`  (Docker internal hostname — NOT localhost)
- Port: `5432`
- Username/Password: from your `.env`

---

## Phase 3 — Initialise Tables

Run this ONCE after starting Postgres for the first time.  
It is safe to re-run — it uses `CREATE TABLE IF NOT EXISTS`.

```bash
python -m app.database.create_tables
```

Expected output:
```
10:00:01 | app.database.session | INFO | Database connection: OK
10:00:01 | __main__ | INFO | Loading models...
10:00:01 | __main__ | INFO | Creating tables (CREATE TABLE IF NOT EXISTS)...
10:00:01 | __main__ | INFO | Tables available: ['articles', 'youtube_videos']
10:00:01 | __main__ | INFO | Done. Database is ready.
```

---

## Schema Migrations (Alembic)

Schema changes go through Alembic migrations — never hand-written `ALTER TABLE`
against a live DB. `python -m app.database.create_tables` (Phase 3 above)
creates the tables AND stamps the DB at the current Alembic head in one step,
so a brand-new dev DB and an existing one always converge on the same
migration state.

To make a schema change:

```bash
# 1. Edit/add a model in app/database/models/
# 2. Generate a migration from the diff
alembic revision --autogenerate -m "add some_column to articles"

# 3. ALWAYS review the generated file in alembic/versions/ before applying —
#    autogenerate is a starting point, not ground truth. In this project
#    specifically, Django owns several tables in the SAME database (users,
#    user_profiles, personas, ...); alembic/env.py's include_object filter
#    excludes them from the diff, but any other unexpected op deserves a
#    second look before it touches the real DB.

# 4. Apply it
alembic upgrade head

# Useful commands
alembic current      # what revision is this DB stamped at
alembic history       # full migration chain
```

Known rough edge for a future migration: `pgvector.sqlalchemy.Vector` is a
custom SQLAlchemy type, and autogenerate isn't guaranteed to emit a correct
import for it in a migration that adds/alters a vector column — check the
generated file's imports if you touch `embeddings.vector` later.

---

## Process Topology

```
                         ┌───────────────────────┐
                         │   PostgreSQL (5433)   │
                         │  pgvector extension   │
                         └───────────┬───────────┘
              writes/reads (own tables only)
           ┌─────────────────────────┼─────────────────────────┐
           │                                                    │
┌──────────▼───────────┐                              ┌─────────▼──────────┐
│  Pipeline (app/)      │                              │  Web (web/, Django) │
│  SQLAlchemy           │◄──── read-only mirrors ─────►│  users/profiles/... │
│  articles, sources,   │      (both directions)       │  personalized /feed  │
│  embeddings, ...      │                              └──────────────────────┘
└──────────┬────────────┘
           │ enqueues via
┌──────────▼────────────┐        ┌───────────────────────┐
│  Redis (6379)          │◄──────►│  Celery worker (main)  │  --pool=solo, DEFAULT queue:
│  broker + result store │        │  app/tasks/*           │  scrape/embed/enrich/cluster/score/
│  DB 0 (pipeline)       │        └───────────────────────┘  affinity/profile-vector/ranking/digest
└──────────┬─────────────┘        ┌───────────────────────┐
           │                      │  Celery worker (M9)    │  --pool=solo -Q interactive: ONLY
           │                      │  interactive queue     │  search_tasks.embed_query_task —
           │                      └───────────────────────┘  never blocked behind a 6h pipeline run
           │ schedules
┌──────────▼─────────────┐
│  Celery beat            │  fires run_full_pipeline_task every 6h, ranking every 3h,
│  (app/celery_app.py)    │  affinity + profile-vector aggregation nightly
└──────────────────────────┘

Django's cache uses a SEPARATE Redis DB (1, not 0) — see REDIS_URL vs.
CELERY_BROKER_URL in web/config/settings/base.py. Django's search.py is a
Celery CLIENT only (no torch/sentence-transformers) — it enqueues onto the
interactive queue above; the actual embedding model runs in the pipeline's
worker process.

Manual/one-off runs still work standalone: `python run_pipeline.py [flags]`
never touches Celery or Redis — it calls the same phase functions directly.
```

---

## Background Jobs (Celery + Redis)

The pipeline's scraping/embedding/digest phases run as Celery tasks
(`app/tasks/`), with Redis as the broker and result backend. The manual CLI
(`python run_pipeline.py`) is untouched and still works for one-off runs —
Celery tasks call the exact same phase functions (`run_scraping_phases`,
`run_embedding_phase`, `run_digest_phase`), never `run_pipeline.main()`.

### Start Redis

```bash
docker compose -f docker/docker-compose.yml up -d redis
```

### Windows dev note — invocation matters

Always use `python -m celery`, never the bare `celery` command, and always
run from the repo root. `run_pipeline.py` is a top-level script (no package,
no editable install) — only `python -m X` adds the current working directory
to `sys.path`, which `app/tasks/pipeline_tasks.py` needs to `import
run_pipeline`. The bare `celery` console-script entry point does not add CWD,
so it can never resolve that import.

Celery's default prefork pool has known issues on Windows — always pass
`--pool=solo` for the worker.

### Run the worker + beat (two separate processes)

```bash
# Terminal 1 — executes tasks (default queue: scrape/enrich/cluster/score/digest/affinity/ranking)
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info

# Terminal 2 — fires the scheduled task every 6 hours (crontab, code-defined,
# no django-celery-beat / no DB-backed schedule table)
python -m celery -A app.celery_app:celery_app beat --loglevel=info
```

### Run a dedicated "interactive" worker (M9 — required for semantic search)

Semantic search (`/search/`) embeds the user's query via a Celery task
(`app.tasks.search_tasks.embed_query_task`) so Django never needs its own
copy of `sentence-transformers`. That task is routed to its own
`interactive` queue and needs its **own worker process** — not the default
queue above, which the 6-hourly full pipeline run can occupy for minutes
at a time (a search request queued behind a running scrape/enrich pass
would simply time out).

```bash
# Terminal 3 — ONLY consumes the interactive queue, stays responsive even
# while the default-queue worker is mid-pipeline-run
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h
```

If this worker isn't running, `/search/` degrades gracefully to keyword
search after a 5s timeout (a visible banner tells the user) — it never 500s.

### Available tasks

| Task | Purpose |
|---|---|
| `app.tasks.health_tasks.ping_task` | Trivial round-trip check |
| `app.tasks.pipeline_tasks.scrape_task` | One source or "all" |
| `app.tasks.pipeline_tasks.embed_task` | Embed unembedded content |
| `app.tasks.pipeline_tasks.digest_task` | Enrich unenriched content (one `EnrichmentAgent` LLM call/item) + build/send digests from each recipient's *current* ranking |
| `app.tasks.pipeline_tasks.cluster_task` | M8: cross-source near-duplicate clustering (Union-Find over pgvector k-NN) |
| `app.tasks.pipeline_tasks.score_task` | M8: heuristic quality scoring for every article/video |
| `app.tasks.pipeline_tasks.run_full_pipeline_task` | scrape → embed → enrich/digest → cluster → score, what beat schedules |
| `app.tasks.affinity_tasks.aggregate_affinities_task` | Nightly (M7, extended M9): raw `user_events` → time-decayed `user_affinities` across source/topic/entity dimensions, then prunes events >90 days old via a `manage.py prune_old_events` subprocess |
| `app.tasks.profile_vector_tasks.compute_profile_vectors_task` | M9: nightly decayed weighted-mean embedding per user (`user_profile_vectors`) from click/save/digest_click events |
| `app.tasks.ranking_tasks.rank_all_users_task` | M9: the two-stage deterministic ranker, on its own 3-hour schedule — decoupled from digest cadence so `/feed` stays fresh |
| `app.tasks.search_tasks.embed_query_task` | M9: embeds a free-text search query — routed to the `interactive` queue only |

Dispatch one manually to confirm the round-trip works:

```bash
python -c "from app.tasks.health_tasks import ping_task; r = ping_task.delay('hi'); print(r.get(timeout=10))"
```

---

## Phase 4 — Run the Pipeline

```bash
# Full pipeline (YouTube + blogs, default 6-day lookback)
python run_pipeline.py

# Only YouTube scraper
python run_pipeline.py --source youtube

# Only blog scraper
python run_pipeline.py --source blogs

# Custom lookback (last 48 hours)
python run_pipeline.py --hours 48

# Dry run — scrape but don't write to DB (useful for testing)
python run_pipeline.py --dry-run

# Combine flags
python run_pipeline.py --source blogs --hours 24 --dry-run
```

Expected summary at end:
```
==============================================================
PIPELINE SUMMARY
==============================================================
  YouTube  : scraped=  12  inserted=  10  skipped=   2  errors=   0
  Articles : scraped=   5  inserted=   4  skipped=   1  errors=   0
  TOTAL    : scraped=  17  inserted=  14  skipped=   3
==============================================================
```

Unless `--dry-run` is passed, every run also does (M8 — Content Intelligence Layer):
1. **Enrichment** — one `EnrichmentAgent` LLM call per unenriched article/video: topics, entities, `content_category`, `technical_depth`, `why_it_matters`, etc. (replaces the old `DigestAgent` summary-only call).
2. **Clustering** — near-duplicate/cross-source grouping via Union-Find over pgvector k-NN neighbors (`content_clusters` / `content_cluster_members`). `huggingface_model` articles are excluded from the candidate pool — their templated auto-generated summaries otherwise "bridge" unrelated uploads into one mega-cluster.
3. **Scoring** — a heuristic quality score (`content_scores`) computed for every article/video, enriched or not.

### Backfilling enrichment for pre-M8 content

Existing articles/videos scraped before M8 have summaries but no `content_enrichment` row. This corpus is **not** backfilled automatically — run it deliberately when ready:

```bash
# Small batch via local Ollama (no API cost) — good for a first pass
python -m app.database.backfill_enrichment --limit 50 --provider local

# Full corpus via Groq
python -m app.database.backfill_enrichment --provider groq
```

Backfilled rows are tagged with a distinct `enrichment_version` (`v1-backfill-ollama` by default via `--version`) so they can be told apart from rows produced by the normal pipeline run.

---

## Phase 5 — Verify Records in the Database

### Via psql (inside Docker)

```bash
# Open a psql shell inside the container
docker exec -it ai_news_db psql -U ai_news_user -d ai_news

# Count rows
SELECT COUNT(*) FROM articles;
SELECT COUNT(*) FROM youtube_videos;

# Preview newest articles
SELECT id, source, title, published_at
FROM articles
ORDER BY published_at DESC
LIMIT 5;

# Preview newest videos
SELECT id, channel_name, title, published_at
FROM youtube_videos
ORDER BY published_at DESC
LIMIT 5;

# Check for articles that still need summarisation
SELECT COUNT(*) FROM articles WHERE summary IS NULL;

# Exit psql
\q
```

### Via Python REPL

```python
from dotenv import load_dotenv
load_dotenv()

from app.database import get_db_session, ArticleRepository, YoutubeRepository

with get_db_session() as db:
    articles = ArticleRepository(db).get_all(limit=5)
    for a in articles:
        print(a)

with get_db_session() as db:
    videos = YoutubeRepository(db).get_all(limit=5)
    for v in videos:
        print(v)
```

---

## Phase 6 — Run Tests

```bash
# All tests
pytest tests/ -v

# Just the database tests (no network needed)
pytest tests/test_database.py -v

# Just the scraper tests
pytest tests/test_scrapers.py -v

# With coverage
pytest tests/ --cov=app --cov-report=term-missing
```

The database tests use an **in-memory SQLite** database — they run instantly
and need no running Postgres.

---

## Development & Operations Guide

> This is the project's canonical operational reference, written for someone
> who has never run this project before. Phases 1-6 above are the "set up
> once" path; this section is what you come back to every day after that —
> startup order, terminal layout, DB exploration, migrations, a command
> cheat sheet, the architecture map, debugging, and a health checklist.
> Everything below is grounded in the actual M9 codebase, not aspirational.

### 1. Complete Startup Workflow (clean machine to fully running system)

Order matters — each step assumes the previous one already succeeded.

**Step 0 — one-time setup** (skip if already done)

```bash
cp .env.example .env              # fill in GROQ_API_KEY at minimum
cp web/.env.example web/.env      # already has sane localhost defaults

# Pipeline deps (root .venv, Python 3.14, managed via uv/pyproject.toml)
uv sync                            # or: pip install -e .

# Django deps (SEPARATE venv — see the note in Section 5 about why)
cd web && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cd ..
```

**Step 1 — Docker services (PostgreSQL + Redis + pgAdmin)**

```bash
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml ps        # confirm db + redis show "healthy"
```

| Service | Container name | Host port | Purpose |
|---|---|---|---|
| `db` | `ai_news_db` | **5433** (maps to 5432 in-container) | Postgres 16 + pgvector. Host port is 5433, not 5432 — a native Windows Postgres install already owns 5432 on this dev machine (see Section 7). |
| `redis` | `ai_news_redis` | 6379 | Celery broker/result backend (pipeline, **DB 0**) *and* Django's cache backend (**DB 1**) — same Redis instance, different logical DB index. Never mix these two up (see Section 7). |
| `pgadmin` | `ai_news_pgadmin` | 5050 (default, `PGADMIN_PORT`) | Optional web UI. |

**Step 2 — Initialize the database** (first time only — safe to re-run, idempotent)

```bash
python -m app.database.create_tables         # CREATE TABLE IF NOT EXISTS + stamps Alembic head
python -m app.database.seed_sources          # 9 Source Registry rows
python -m app.database.seed_taxonomy_topics  # 27 taxonomy topics (M8)
cd web && python manage.py migrate && cd ..
```

**Step 3 — Django development server** (required to browse the site)

```bash
cd web
web/.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

→ http://127.0.0.1:8000

**Step 4 — Celery worker, default queue** (required for scheduled scrape/enrich/rank/digest — NOT required just to browse)

```bash
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info
```

**Step 5 — Interactive worker** (M9 — required for semantic search only)

```bash
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h
```

Without this, `/search/` still works — it degrades to keyword search after a 5s timeout, with a visible banner.

**Step 6 — Celery beat** (required only if you want the schedules below to fire automatically)

```bash
python -m celery -A app.celery_app:celery_app beat --loglevel=info
```

**Step 7 — Pipeline CLI** (on-demand, whenever you want fresh content or to force a phase)

```bash
python run_pipeline.py                    # full run: scrape -> enrich -> digest -> cluster -> score
python run_pipeline.py --skip-scraping    # re-process what's already in the DB
```

That's a fully running system: Postgres + Redis + pgAdmin in Docker, Django
serving the site, two Celery workers, beat firing the schedule, and the
pipeline CLI available on demand.

---

### 2. Recommended Terminal Layout

| Terminal | Runs | Required? |
|---|---|---|
| 1 | Docker (`up -d`, then leave it — or just check `ps` occasionally) | Required once |
| 2 | Django dev server | Required to browse the site |
| 3 | Celery worker (default queue) | Required for scheduled/background jobs; not required if you only ever trigger things manually |
| 4 | Celery worker (interactive queue) | Required for semantic search; everything else works without it |
| 5 | Celery beat | Required only for schedules to fire automatically — never required for manual/dev work |
| 6 | Manual pipeline runs, `manage.py shell`, ad-hoc debugging | Optional, as-needed |

**Minimum viable dev loop** (browse the site + trigger things manually, no
background automation): Terminals **1 and 2** only, running
`python run_pipeline.py` by hand in a spare terminal whenever you want new
content.

**Full production-like loop**: all 6.

---

### 3. Database Exploration

**Connect via pgAdmin**: http://localhost:5050, log in with `PGADMIN_EMAIL`
/`PGADMIN_PASSWORD` (defaults: `admin@local.dev` / `admin`), then
"Add Server":

- Host: `db` (the Docker Compose **service name** — not `localhost`; pgAdmin
  runs inside the same Docker network and resolves other services by name)
- Port: `5432` (the container's *internal* port — not the host-mapped 5433)
- Database: `ai_news`, user `ai_news_user`, password from `POSTGRES_PASSWORD`

Everything lives in the `public` schema of one database — no separate
schema per app.

**Table ownership map** (verified against the actual model files, M9):

| Owner | Tables | Migrated by |
|---|---|---|
| Pipeline (SQLAlchemy) | `articles`, `youtube_videos`, `embeddings`, `sources`, `user_rankings`, `digest_log`, `user_affinities`, `digest_click_tokens`, `taxonomy_topics`, `content_topics`, `entities`, `content_entities`, `content_clusters`, `content_cluster_members`, `content_enrichment`, `content_scores`, `user_profile_vectors` | Alembic |
| Django | `users`, `user_profiles`, `personas`, `interests`, `user_interests`, `user_digest_settings`, `user_exclusions`, `user_events`, `saved_items`, `user_follows` | Django migrations |

**Read-only mirrors** (same physical table, read from the *other* ORM,
never migrated or written by it):

- Django reads pipeline tables via `web/apps/catalog/models.py`
  (`managed = False`) — all 17 pipeline tables above **except**
  `user_profile_vectors` (no Django mirror exists yet; only the pipeline
  reads it today).
- The pipeline reads Django tables via
  `app/database/models/django_readmodels.py` (a separate `DjangoBase`) —
  all 10 Django tables above **except** `saved_items` (nothing in the
  pipeline needs it yet).

**Populated by background jobs, not by request handlers:**

| Table | Written by |
|---|---|
| `user_affinities` | `aggregate_affinities_task` (nightly, 3:00 UTC) |
| `user_profile_vectors` | `compute_profile_vectors_task` (nightly, 3:15 UTC) |
| `user_rankings` | `rank_all_users_task` (every 3h) — or an on-demand cold-start inside `DigestService` |
| `content_clusters` / `content_cluster_members` | the pipeline's clustering phase (every `run_pipeline.py` run, unless `--dry-run`) |
| `content_scores` | the pipeline's scoring phase (same) |
| `content_enrichment` / `content_topics` / `content_entities` | `DigestService._enrich_unenriched()` (every pipeline run, one LLM call per item) |
| `embeddings` | the embed phase, and re-embedded whenever enrichment writes a fresh summary |
| `digest_click_tokens` | minted at digest-build time |
| `digest_log` | one row per actual email send |

**Connect via `psql`** (inside Docker — no local `psql` install needed):

```bash
docker exec -it ai_news_db psql -U ai_news_user -d ai_news
```

Or via Django (needs a local `psql` client on PATH):

```bash
cd web && python manage.py dbshell
```

**Common debugging queries:**

```sql
-- List all tables
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Table schema (columns, types, nullability, defaults)
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'user_rankings' ORDER BY ordinal_position;

-- Row counts, biggest tables first (fast estimate, not an exact COUNT(*))
SELECT relname AS table_name, n_live_tup AS row_estimate
FROM pg_stat_user_tables ORDER BY n_live_tup DESC;

-- Indexes on a table
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'content_topics';

-- Foreign keys on a table (most cross-ORM references are PLAIN INTEGERS by
-- convention, not real DB-level FKs — see .wolf/cerebrum.md — so this will
-- often come back empty even where a logical relationship exists)
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
WHERE conrelid = 'content_topics'::regclass AND contype = 'f';

-- Recent articles
SELECT id, title, source, published_at
FROM articles ORDER BY published_at DESC LIMIT 20;

-- A user's current ranking
SELECT rank, content_type, content_id, relevance_score, score_version, reasoning
FROM user_rankings WHERE user_id = 1 ORDER BY rank;

-- A user's affinities across all 3 dimensions (source/topic/entity)
SELECT dimension, key, weight
FROM user_affinities WHERE user_id = 1 ORDER BY dimension, weight DESC;

-- A user's profile vector (existence + freshness — not the raw 384 floats)
SELECT user_id, sample_size, model_name, updated_at
FROM user_profile_vectors WHERE user_id = 1;

-- Embeddings for one item
SELECT content_type, content_id, model_name, created_at
FROM embeddings WHERE content_type = 'article' AND content_id = 6774;

-- Clusters and their members
SELECT cluster_id, content_type, content_id, similarity_to_centroid
FROM content_cluster_members ORDER BY cluster_id;

-- Quality scores, worst first (sanity-check the scoring formula)
SELECT content_type, content_id, score, features
FROM content_scores ORDER BY score ASC LIMIT 10;

-- Recent user events (M7 instrumentation)
SELECT user_id, event_type, content_type, content_id, value, created_at
FROM user_events ORDER BY created_at DESC LIMIT 20;

-- Saved / read / hidden state for a user
SELECT content_type, content_id, is_saved, is_read, is_hidden
FROM saved_items WHERE user_id = 1;

-- What a user follows (M9)
SELECT target_type, target_key, created_at
FROM user_follows WHERE user_id = 1;

-- Digest click tokens (has anyone clicked through from an email?)
SELECT token, user_id, content_type, content_id, created_at
FROM digest_click_tokens ORDER BY created_at DESC LIMIT 10;
```

---

### 4. Alembic & Django Migrations — When to Use Which

This project uses **two migration systems** because it uses **two ORMs
owning disjoint sets of tables** (Architecture Principle 2 in
`docs/ROADMAP.md`) — Alembic for everything SQLAlchemy/pipeline-owned,
Django migrations for everything Django-owned. Neither ORM ever migrates
the other's tables — enforced by `alembic/env.py`'s `include_object` filter
and Django's `PipelineRouter.allow_migrate`, both of which are load-bearing,
not incidental.

**Alembic (pipeline — `app/`)**

```bash
# After changing/adding a model in app/database/models/:
alembic revision --autogenerate -m "add some_field to some_table"

# ALWAYS review the generated file by hand before applying it — autogenerate
# has produced incorrect output before on this project (a missing import,
# a proposed DROP of every Django-owned table). See .wolf/buglog.json
# pipeline-013 and pipeline-017.

alembic upgrade head          # apply
alembic check                 # verify zero drift — run after every upgrade
alembic downgrade -1          # roll back one revision
alembic current                # what revision is this DB on
alembic history                 # full revision history

# Stamp an EXISTING database as current WITHOUT running any DDL — only for
# baselining a DB that already has the right schema (a fresh
# create_tables.py run, or recovering from a manual fix).
alembic stamp head
```

**Django migrations (`web/`)**

```bash
cd web

python manage.py makemigrations                        # after changing web/apps/*/models.py
python manage.py migrate                                 # apply
python manage.py makemigrations --check --dry-run        # verify nothing is un-migrated
python manage.py sqlmigrate onboarding 0005               # preview a migration's SQL without running it
```

**Rule of thumb:** if the model lives in `app/database/models/`, it's
Alembic. If it lives in `web/apps/*/models.py` and is **not**
`managed = False`, it's Django migrations. `managed = False` models (the
cross-ORM read mirrors) are never migrated by anything — running
`makemigrations`/`revision --autogenerate` against them is a harmless no-op
that's already committed; you should never see new output for them.

---

### 5. Common Development Commands (cheat sheet)

```bash
# ---- Pipeline ----
python run_pipeline.py                                # full run
python run_pipeline.py --source youtube                # only YouTube
python run_pipeline.py --source arxiv --skip-digest    # only scrape arXiv; clustering/scoring still run
python run_pipeline.py --skip-scraping                  # re-enrich/cluster/score what's already in the DB
python run_pipeline.py --dry-run                        # scrape only, write nothing (also skips clustering/scoring)

# ---- Enrichment backfill (M8 — pre-M8 rows have summaries but no content_enrichment row) ----
python -m app.database.backfill_enrichment --limit 50 --provider local   # Ollama, zero API cost
python -m app.database.backfill_enrichment --provider groq                # full corpus, Groq

# ---- Ranking (M9) — recompute on demand, without waiting for the 3h schedule ----
python -c "from app.tasks.ranking_tasks import rank_all_users_task; print(rank_all_users_task.run())"
# ...or dispatch through Celery instead of running inline (needs a running default-queue worker):
python -c "from app.tasks.ranking_tasks import rank_all_users_task; r = rank_all_users_task.delay(); print(r.get(timeout=120))"

# ---- Profile vectors / affinities (M7 / M9) — recompute on demand ----
python -c "from app.tasks.profile_vector_tasks import compute_profile_vectors_task; print(compute_profile_vectors_task.run())"
python -c "from app.tasks.affinity_tasks import aggregate_affinities_task; print(aggregate_affinities_task.run())"

# ---- Semantic search — smoke-test the embedding step directly (no Celery needed) ----
python -c "from app.embeddings.embedding_service import embed_text; print(len(embed_text('test query')))"

# ---- Tests ----
pytest                                                  # full suite (root .venv)
pytest tests/test_database.py                           # one file
pytest tests/test_agents.py::TestEnrichmentAgent -v      # one test class, verbose
pytest -k "ranking"                                     # by keyword

# ---- Django ----
cd web
python manage.py check                                   # system check
python manage.py makemigrations --check --dry-run
python manage.py shell                                    # Python shell, Django app registry loaded
python manage.py dbshell                                  # psql, if installed locally
python manage.py collectstatic                            # PRODUCTION ONLY — dev serves static files directly from source; skip this locally
python manage.py createsuperuser
python manage.py prune_old_events                         # manual retention prune (normally run nightly by Celery)

# ---- Seeding ----
python -m app.database.seed_sources                       # Source Registry (9 rows)
python -m app.database.seed_taxonomy_topics                # Taxonomy (27 rows)

# ---- Restarting workers ----
# Celery workers do NOT hot-reload code. After editing anything under
# app/tasks/ (or a module it imports), Ctrl+C the worker process and start
# it again — a still-running worker silently keeps executing the OLD code.
```

---

### 6. Project Architecture Map

**Celery queues:**

- **`celery`** (default) — scrape, embed, enrich, cluster, score, digest,
  nightly affinity aggregation, nightly profile-vector computation, and
  ranking. One worker process, `--pool=solo`.
- **`interactive`** (M9) — **only** `search_tasks.embed_query_task`. A
  SEPARATE worker process, so a search request never queues behind a
  multi-minute pipeline run on the default queue.

**Scheduled jobs** (Celery beat — all crontab, code-defined in
`app/celery_app.py`, no DB-backed schedule table):

| Job | Schedule | Type |
|---|---|---|
| `run_full_pipeline_task` | every 6h | batch |
| `aggregate_affinities_task` | nightly, 3:00 UTC | nightly batch |
| `compute_profile_vectors_task` | nightly, 3:15 UTC | nightly batch |
| `rank_all_users_task` | every 3h | periodic batch |

**Interactive (request-time) jobs**: only `embed_query_task`. Everything
else above is background/batch — nothing else is ever invoked synchronously
from a web request (Architecture Principle 6: no LLM or heavy compute in a
request's hot path; M9 extends this to ranking too, except for the
one-time cold-start fallback inside `DigestService`).

```mermaid
flowchart TB
    subgraph Docker
        PG[("PostgreSQL :5433<br/>+ pgvector")]
        RD[("Redis :6379<br/>DB0=Celery, DB1=Django cache")]
        PGA["pgAdmin :5050"]
    end

    subgraph Pipeline["Pipeline (app/) - SQLAlchemy"]
        RP["run_pipeline.py CLI"]
        CW1["Celery worker<br/>default queue"]
        CW2["Celery worker<br/>interactive queue"]
        BEAT["Celery beat"]
    end

    subgraph Web["Web (web/) - Django"]
        DJ["Django dev server :8000"]
        SEARCH["apps/news/search.py<br/>Celery CLIENT only"]
    end

    RP -->|writes| PG
    CW1 -->|writes| PG
    BEAT -->|schedules| CW1
    CW1 <-->|broker/backend DB0| RD
    CW2 <-->|broker/backend DB0| RD
    SEARCH -->|enqueue embed_query_task| RD
    RD --> CW2
    DJ -->|reads pipeline tables read-only| PG
    DJ -->|cache DB1| RD
    DJ -->|writes own tables| PG
```

---

### 7. Debugging Guide

**Redis not running** — `docker compose -f docker/docker-compose.yml ps`
shows `redis` unhealthy or absent.
→ `docker compose -f docker/docker-compose.yml up -d redis`. Confirm with
`docker exec ai_news_redis redis-cli ping` → `PONG`.

**Celery worker offline / a task sits in PENDING forever**
→ Check that a worker is actually consuming the queue the task was routed
to — `search_tasks.*` is routed to the `interactive` queue specifically; a
default-queue-only worker will never pick it up. Confirm reachability:
`python -c "from app.celery_app import celery_app; print(celery_app.control.ping(timeout=2.0))"`
— an empty list means no worker is reachable at all.

**Semantic search unavailable / always falls back to keyword search**
→ The interactive worker isn't running, or crashed loading
`sentence-transformers`. Start it:
`python -m celery -A app.celery_app:celery_app worker --pool=solo -Q interactive -n interactive-worker@%h`.
The fallback itself is by design, not a bug — but if it's *persistent*, the
worker needs attention.

**pgvector issues** (`can't render element of type VECTOR` /
`type "vector" does not exist`)
→ The extension isn't enabled on this DB — run
`python -m app.database.create_tables` (idempotent, enables it). If writing
a brand-new Alembic migration that creates its FIRST pgvector `Vector`
column, add `import pgvector.sqlalchemy` to the generated file by hand —
autogenerate does not add this import automatically (see buglog
pipeline-017).

**Ollama unavailable** (`LLM_PROVIDER=local` but connection refused on
`:11434`)
→ Ollama isn't running, or the model isn't pulled. Start Ollama, then
`ollama pull llama3.1:8b` (or whatever `LOCAL_SIMPLE_MODEL` names). Note:
ranking (M9) never uses an LLM at all — this only affects
`EnrichmentAgent`/`EmailAgent`'s "simple" tier.

**Groq unavailable** (401/429, or `KeyError: 'GROQ_API_KEY'`)
→ Set `GROQ_API_KEY` in `.env`, or set `LLM_PROVIDER=local` to run
enrichment via Ollama instead (zero API cost — see
`app/database/backfill_enrichment.py --provider local`). 429s are rate
limits; `EnrichmentAgent._call_with_backoff()` already retries with
exponential backoff — if it still fails after 4 retries, wait or switch
providers.

**Migration drift** (`alembic check` or `makemigrations --check --dry-run`
reports changes)
→ A model changed without a matching migration. Alembic:
`alembic revision --autogenerate -m "..."`, review, `alembic upgrade head`.
Django: `python manage.py makemigrations`, review,
`python manage.py migrate`. Never hand-edit the schema directly.

**Docker issues** ("port is already allocated", containers won't start)
→ Port 5432 is very likely owned by a native Postgres install on this
machine — that's *why* this project maps to host port 5433 instead (see
`docker-compose.yml`'s own comment, and buglog `db-001`). Don't fight to
free 5432; use 5433 everywhere, which is already the default in both
`.env` files.

**Empty rankings** (`/feed` shows the un-personalized fallback;
`user_rankings` has no rows for a user)
→ Expected for a brand-new user before `rank_all_users_task` has ever run
for them — `DigestService` computes one on-demand the first time a digest
is *built*, but visiting `/feed` alone doesn't trigger that. Force it:
`python -c "from app.tasks.ranking_tasks import rank_all_users_task; print(rank_all_users_task.run())"`.

**Empty recommendations / the same items every time**
→ Check the user actually has engagement events (`user_events`) and/or
onboarding `Interest` selections — with neither, candidate generation falls
back to freshness+quality only (an honest, less-personalized result, not a
bug). Check `user_affinities`/`user_profile_vectors` have rows for that
`user_id`.

**Empty search results**
→ First check whether the response's `used_semantic` was `true` or
`false`. If `false`, the interactive worker is down (see above) and it's
doing a literal keyword match, which can legitimately return nothing for a
query with no exact keyword hits. If `true` and results are still empty,
check `embeddings` actually has rows: `SELECT count(*) FROM embeddings;`.

---

### 8. Verification Checklist ("is my system healthy?")

- [ ] `docker compose -f docker/docker-compose.yml ps` — `db` and `redis`
      both show `healthy`
- [ ] `python manage.py check` (from `web/`) — 0 issues
- [ ] `alembic check` — "No new upgrade operations detected"
- [ ] `python manage.py makemigrations --check --dry-run` — "No changes detected"
- [ ] `python -c "from app.celery_app import celery_app; print(celery_app.control.ping())"`
      — at least one worker responds
- [ ] The default-queue worker's startup log shows `[queues] .> celery`, and
      the interactive worker's shows `.> interactive` — confirms they're
      NOT both listening on the same queue
- [ ] `curl -I http://127.0.0.1:8000/` → `200 OK`
- [ ] `/search/?q=...` for a real query returns `used_semantic: true`
      (confirms the interactive worker + pgvector round trip both work)
- [ ] `/feed` renders ranked items with real `reasoning` text for a user
      who has `user_rankings` rows
- [ ] `SELECT count(*) FROM articles;` / `youtube_videos` / `embeddings` —
      all non-zero, roughly proportional to each other
- [ ] `pytest` — **14 passed, 22 pre-existing errors** (the SQLite/JSONB
      baseline — see the Do-Not-Repeat section of `.wolf/cerebrum.md`; any
      other failure count is a real regression, not this baseline)

---

## Common Mistakes and Fixes

### "could not connect to server"
- PostgreSQL isn't running: `docker compose -f docker/docker-compose.yml up -d`
- Wrong `POSTGRES_HOST`: must be `localhost` from the host machine

### "relation 'articles' does not exist"
- You haven't run `python -m app.database.create_tables` yet

### "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed"
- A duplicate URL was inserted. This should not happen if you use `bulk_create`
  (which has `ON CONFLICT DO NOTHING`). If using `create()` in a loop, it
  already calls `exists_by_url()` first.

### "column 'published_at' ... naive datetime"
- Your scraper returned a datetime without timezone info.
- The `_ensure_tz()` helper in each repository fixes this automatically.
- If you see this error, check that your scraper sets `tzinfo=timezone.utc`.

### "ModuleNotFoundError: No module named 'app'"
- Run from the project root: `python run_pipeline.py`
- Or set `PYTHONPATH=.` in your shell: `PYTHONPATH=. pytest tests/`

### pgAdmin can't connect to "localhost"
- Inside Docker, the Postgres container is named `db`, not `localhost`.
- Use `db` as the hostname in pgAdmin's "Add Server" dialog.

---

## Production Deployment Checklist

- [ ] Change all default passwords in `.env`
- [ ] Set `POSTGRES_HOST` to your RDS / Cloud SQL endpoint
- [ ] Remove the `pgadmin` service from docker-compose.yml
- [ ] Set `LOG_LEVEL=WARNING` in production `.env`
- [ ] Run the pipeline via Celery beat instead of a raw cron entry (see
      "Background Jobs" below) — cron/manual `run_pipeline.py` still works
      as a fallback for one-off runs.
- [ ] Add monitoring: alert if pipeline exits with code 1 (errors occurred)