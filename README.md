# AI News Aggregator (AI Compass) — Setup & Operations Guide

Complete guide to spinning up the database, running the pipeline, serving the
web app and the frontend, and verifying everything works end to end.

**Preparing for a project defense / want to understand the system deeply?**
Read [`docs/PROJECT_DEEP_DIVE_AND_VIVA.md`](docs/PROJECT_DEEP_DIVE_AND_VIVA.md)
— a code-derived walkthrough of every stage, every formula, every model, every
failure path, plus ~80 exam questions with answers.

**Deploying to production?** See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
for the full $0/month deployment guide (Oracle Cloud + Docker Compose
primary path, Render + GitHub Actions fallback path, database migration
with zero data loss, redeploy/rollback procedures, and known limitations).

**In a hurry?** Jump straight to the
[Complete Command Reference](#complete-command-reference) near the end.

---

## Project Layout

```
ai-news-aggregator/
├── app/                                 # PIPELINE — SQLAlchemy, Python 3.14, all ML deps
│   ├── config.py                        # Infra settings only (business data lives in the DB)
│   ├── celery_app.py                    # Celery app: queues, routes, beat schedule
│   ├── scrapers/                        # base + blog, youtube, rss, arxiv, github, federal_register, huggingface
│   ├── agents/                          # enrichment, assistant (RAG), trend_narrative, chunk_summary, email
│   ├── services/                        # digest, ranking, rag, recipients, relevance_gate, stt, email_sender
│   ├── embeddings/embedding_service.py  # all-MiniLM-L6-v2, 384-dim, LOCAL
│   ├── rag/chunker.py                   # passage chunking (~180 tok, 40 overlap)
│   ├── ranking/types.py                 # UserProfile / DigestItem / RankedArticle
│   ├── llm/client_factory.py            # the ONE Groq-vs-Ollama routing decision
│   ├── eval/ranking_eval.py             # NDCG@10 / MAP / shadow-mode comparison
│   ├── tasks/                           # 11 Celery task modules
│   └── database/
│       ├── session.py                   # Engine + SessionLocal + get_db_session()
│       ├── create_tables.py             # One-time init: extension + create_all + alembic stamp
│       ├── seed_sources.py              # Source Registry (11 rows)
│       ├── seed_taxonomy_topics.py      # Controlled topic vocabulary (~27 rows)
│       ├── models/                      # 23 SQLAlchemy models + django_readmodels.py (read-only mirror)
│       └── repositories/                # 22 repositories over BaseRepository[T]
├── web/                                 # DJANGO 5.2 — Python 3.13, ZERO ML deps, own venv
│   ├── apps/accounts/                   # User (email login), profiles, entitlements, Stripe
│   ├── apps/onboarding/                 # personas, interests, digest settings, exclusions, subscriptions
│   ├── apps/behavior/                   # user_events, saved_items, user_follows, rate limiting
│   ├── apps/catalog/                    # READ-ONLY mirrors of 22 pipeline tables (managed=False)
│   ├── apps/news/                       # JSON API (11 endpoints), semantic search, home ranking
│   ├── apps/assistant/                  # RAG chat: non-streaming + SSE streaming
│   └── config/                          # settings/{base,dev,prod}.py, urls.py, routers.py
├── frontend/                            # NEXT.JS 16 SPA — React 19, Tailwind 4, shadcn/ui
│   └── src/{app,components,lib}/        # 24 routes, page components, api.ts, store.ts
├── docker/
│   ├── docker-compose.yml               # DEV: postgres + redis + worker-default + worker-stt + beat + pgadmin
│   ├── docker-compose.prod.yml          # PROD: redis + web + chat + frontend + 3 workers + beat + caddy
│   └── Caddyfile                        # TLS + path routing
├── alembic/                             # Pipeline migrations (Django has its own)
├── tests/                               # pytest — SQLite-backed DB tests + scraper tests
├── docs/
│   ├── PROJECT_DEEP_DIVE_AND_VIVA.md    # full technical deep dive + defense prep
│   ├── DEPLOYMENT.md
│   ├── ROADMAP.md
│   └── USER_GUIDE.md
├── run_pipeline.py                      # Pipeline CLI + the phase functions Celery imports
├── Dockerfile                           # pipeline image (Python 3.14)
├── .env.example                         # pipeline env template
└── pyproject.toml
```

---

## Phase 1 — Environment Setup

### 1. Copy and fill the environment files

There are **two** env files — one per codebase.

```bash
cp .env.example .env              # pipeline (app/, run_pipeline.py, Celery)
cp web/.env.example web/.env      # Django (already has sane localhost defaults)
```

Root `.env` — the variables that actually matter:

```ini
# --- Database (the pipeline connects on host port 5433, see docker-compose.yml) ---
POSTGRES_DB=ai_news
POSTGRES_USER=ai_news_user
POSTGRES_PASSWORD=changeme_in_production
DATABASE_URL=postgresql+psycopg2://ai_news_user:changeme_in_production@localhost:5433/ai_news

# --- Redis: Celery broker + result backend (DB 0). Django's cache uses DB 1. ---
REDIS_URL=redis://127.0.0.1:6379/0

# --- Django base URL, used to build tracked digest-click links /r/<token>/ ---
DJANGO_BASE_URL=http://127.0.0.1:8000

# --- LLM: Groq is the default provider. NOT OpenAI. ---
GROQ_API_KEY=gsk_...
LLM_PROVIDER=groq                 # "groq" (default) | "local" (Ollama, "simple" tier ONLY)
LOCAL_SIMPLE_MODEL=llama3.1:8b    # used only when LLM_PROVIDER=local

# --- Digest email (Gmail app password, NOT your account password) ---
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# --- Pipeline behaviour ---
HOURS_LOOKBACK=144                # 6 days — the REAL lookback window
LOG_LEVEL=INFO

# --- Speech-to-text (M12), local faster-whisper ---
WHISPER_MODEL=distil-large-v3     # or distil-medium.en / small / tiny for speed

# --- Optional: residential proxy for YouTube / Anthropic scraping ---
RESIDENTIAL_PROXY_URL=
```

> **Note:** this project uses **Groq**, not OpenAI. There is no `OPENAI_API_KEY`
> anywhere in the codebase — the `openai` SDK is imported only as an
> OpenAI-*compatible* client for Ollama (`http://localhost:11434/v1`).

`web/.env` needs at minimum:

```ini
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=True
DATABASE_URL=postgres://ai_news_user:changeme_in_production@localhost:5433/ai_news
REDIS_URL=redis://127.0.0.1:6379/1          # Django cache — DB 1, NOT 0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0  # Celery broker — DB 0, NOT 1
GROQ_API_KEY=                                # only needed for STREAMING chat
GMAIL_ADDRESS=                                # optional: real verification/reset emails
GMAIL_APP_PASSWORD=
STRIPE_SECRET_KEY=                            # optional: billing degrades honestly without these
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID_PRO=
```

### 2. Install dependencies (three separate environments)

```bash
# 1) Pipeline — root .venv, Python 3.14, managed by uv
uv sync

# 2) Django — SEPARATE venv on Python 3.13
cd web && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && cd ..

# 3) Frontend — Node
cd frontend && npm install && cd ..

# Playwright's headless Chromium (needed by BlogScraper for anthropic.com)
uv run playwright install chromium
```

> **Why three environments?** The pipeline needs torch / sentence-transformers /
> faster-whisper / Playwright; Django deliberately has **zero** ML dependencies
> so it stays small and fast. They also run different Python versions (3.14 vs
> 3.13 — Django 5.2 officially targets ≤ 3.13).

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
# 1) Pipeline tables: enables pgvector, creates 23 tables, stamps Alembic head
python -m app.database.create_tables

# 2) Seed the Source Registry (11 rows) and the topic vocabulary (~27 rows)
python -m app.database.seed_sources
python -m app.database.seed_taxonomy_topics

# 3) Django tables
cd web && .venv/Scripts/python.exe manage.py migrate && cd ..
```

Expected output from step 1:
```
10:00:01 | app.database.session | INFO | Database connection: OK
10:00:01 | __main__ | INFO | Enabling pgvector extension...
10:00:01 | __main__ | INFO | pgvector extension enabled
10:00:01 | __main__ | INFO | Loading models...
10:00:01 | __main__ | INFO | Creating tables (CREATE TABLE IF NOT EXISTS)...
10:00:01 | __main__ | INFO | Tables available: ['articles', 'youtube_videos', 'embeddings',
  'rag_chunks', 'sources', 'user_rankings', 'digest_log', 'user_affinities',
  'digest_click_tokens', 'taxonomy_topics', 'content_topics', 'entities', 'content_entities',
  'content_clusters', 'content_cluster_members', 'content_enrichment', 'content_scores',
  'user_profile_vectors', 'person_entities', 'trends', 'trend_reports', 'content_chunks', 'stt_jobs']
10:00:01 | __main__ | INFO | Stamping Alembic head (schema changes go through migrations from here on)...
Done. Database is ready (schema + Alembic state both current).
```

`create_tables.py` is idempotent (`CREATE TABLE IF NOT EXISTS`) and ends by
running `alembic stamp head`, so a brand-new dev DB and an already-migrated one
converge on the same Alembic state.

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
                         │   PostgreSQL (5433)   │   dev: Docker (pgvector/pgvector:pg16)
                         │  pgvector extension   │   prod: managed Neon
                         └───────────┬───────────┘
              writes/reads (own tables only)
           ┌─────────────────────────┼─────────────────────────┐
           │                                                    │
┌──────────▼───────────┐                              ┌─────────▼──────────────┐
│  Pipeline (app/)      │                              │  Web (web/, Django 5.2) │
│  SQLAlchemy, Py 3.14  │◄──── read-only mirrors ─────►│  users/profiles/events  │
│  ML deps: torch,      │      (both directions)       │  ZERO ML deps           │
│  sentence-transformers│                              │  JSON API + auth + chat │
│  faster-whisper,      │                              └─────────┬───────────────┘
│  playwright           │                                         │ same-origin
└──────────┬────────────┘                              ┌─────────▼───────────────┐
           │ enqueues via                              │  Frontend (Next.js 16)   │
┌──────────▼────────────┐                              │  :3000 dev / container   │
│  Redis (6379)          │                              └──────────────────────────┘
│  DB 0 = Celery broker  │
│  DB 1 = Django cache   │
└──────────┬─────────────┘
           │  ┌──────────────────────────┐  --pool=solo, DEFAULT queue:
           ├─►│ Celery worker (default)   │  scrape / stt-dispatch / embed / enrich /
           │  └──────────────────────────┘  digest / deep-video / rag-index / cluster /
           │                                 score / trends / affinity / profile-vector / ranking
           │  ┌──────────────────────────┐  -Q interactive: embed_query_task,
           ├─►│ Celery worker (interactive)│  rag_answer_task, rag_retrieve_task,
           │  └──────────────────────────┘  evaluate_and_register_source_task
           │  ┌──────────────────────────┐  -Q stt: transcribe_video_task
           ├─►│ Celery worker (stt)       │  (yt-dlp + faster-whisper, CPU-heavy)
           │  └──────────────────────────┘
           │ schedules
┌──────────▼─────────────┐  run_full_pipeline_task  every 6h  (crontab 0 */6, UTC)
│  Celery beat            │  rank_all_users_task      every 3h  (crontab 30 */3)
│  (app/celery_app.py)    │  aggregate_affinities      03:00    profile vectors 03:15
│  code-defined crontabs  │  revalidate_user_sources   1st @ 04:00
│  NO django-celery-beat  │  weekly trend report       Mon @ 06:00
└──────────────────────────┘

Key facts:
• Django's cache uses a SEPARATE Redis DB (1, not 0) — see REDIS_URL vs.
  CELERY_BROKER_URL in web/config/settings/base.py. Mixing them is a known bug class.
• Django's search.py / rag_client.py / source_submission.py are Celery CLIENTS only
  (no torch, no sentence-transformers) — they enqueue onto the interactive queue;
  the actual models run in the pipeline's worker process.
• broker_transport_options.visibility_timeout is raised to 6 HOURS: a full pipeline run
  takes ~88 minutes and the Redis default of 1 hour caused constant task re-delivery.
• Manual/one-off runs work standalone: `python run_pipeline.py [flags]` never touches
  Celery or Redis — it calls the same phase functions directly.
• In PRODUCTION, Caddy path-routes ONE domain across three services:
    /assistant/stream/*  -> chat:8001    (uvicorn/ASGI, SSE, flush_interval -1, no gzip)
    /api /admin /accounts /behavior /assistant /healthz /r /static -> web:8000 (gunicorn)
    everything else      -> frontend:3000 (Next.js standalone)
  Because it's one origin, this project has NO CORS package anywhere.
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
# Terminal 1 — executes tasks (default queue: scrape/stt-dispatch/embed/enrich/
# deep-video/cluster/score/digest/affinity/ranking)
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info

# Terminal 2 — fires the scheduled task every 6 hours (crontab, code-defined,
# no django-celery-beat / no DB-backed schedule table)
python -m celery -A app.celery_app:celery_app beat --loglevel=info
```

### Run a dedicated "interactive" worker (REQUIRED for search, RAG chat, and add-a-source)

Three user-facing features enqueue work synchronously and wait for a result:

| Feature | Task | Client timeout |
|---|---|---|
| Semantic search (`/search`) | `search_tasks.embed_query_task` | 5 s |
| **RAG chat** (`/assistant/message/`) | `rag_tasks.rag_answer_task` | 25 s |
| **RAG chat streaming** (`/assistant/stream/`) | `rag_tasks.rag_retrieve_task` | 15 s |
| Add a source | `source_submission_tasks.evaluate_and_register_source_task` | 20 s |

All are routed to the `interactive` queue and need their **own worker
process** — not the default queue above, which the 6-hourly full pipeline run
can occupy for minutes at a time (a request queued behind a running
scrape/enrich pass would simply time out).

```bash
# Terminal 3 — ONLY consumes the interactive queue, stays responsive even
# while the default-queue worker is mid-pipeline-run
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h
```

Behaviour without this worker:
- `/search` degrades gracefully to keyword search after a 5 s timeout and
  returns `usedSemantic: false` so the UI can show an honest banner — never a 500.
- **RAG chat returns HTTP 503** ("temporarily unavailable"). There is deliberately
  no fallback — there's no sane keyword substitute for a generated, cited answer.
- "Add a source" times out with an error message.

> ⚠️ `docker/docker-compose.yml` (dev) does **not** define an interactive worker
> service — only `worker-default`, `worker-stt`, and `beat`. If you run the dev
> compose stack alone, you must start this worker on the host. The production
> compose file (`docker-compose.prod.yml`) *does* include `worker-interactive`.

### Run a dedicated "stt" worker (M12 — speech-to-text for caption-less video)

`app.tasks.stt_tasks.transcribe_video_task` (yt-dlp audio pull + local
`faster-whisper` CPU transcription) can take minutes per video — it has its
own `stt` queue so it never blocks the default queue's 6-hourly pipeline
chain. Per the roadmap's own infra note, this worker ideally runs from a
**residential IP** (yt-dlp is more likely to get rate-limited/blocked from a
datacenter IP) — this dev machine qualifies.

```bash
# Terminal 4 — ONLY consumes the stt queue
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q stt -n stt-worker@%h
```

If no worker consumes this queue, queued jobs simply wait — `stt_jobs.status`
stays `'running'` (claimed by the dispatch phase) until a worker picks them
up; nothing else in the pipeline depends on STT completing promptly. Measured
go/no-go throughput on this dev machine: `distil-large-v3` (the default,
override via `WHISPER_MODEL` env var) runs at ~1.76x real-time on CPU/int8 (a
1013s video took 1778s to transcribe) — STT lagging behind ingestion is
expected/accepted at this project's scale, not a bug.

### Available tasks

| Task | Purpose |
|---|---|
| `app.tasks.health_tasks.ping_task` | Trivial round-trip check |
| `app.tasks.pipeline_tasks.scrape_task` | One source or "all" |
| `app.tasks.pipeline_tasks.embed_task` | Embed unembedded content |
| `app.tasks.pipeline_tasks.digest_task` | Enrich unenriched content (one `EnrichmentAgent` LLM call/item) + build/send digests from each recipient's *current* ranking |
| `app.tasks.pipeline_tasks.cluster_task` | M8: cross-source near-duplicate clustering (Union-Find over pgvector k-NN) |
| `app.tasks.pipeline_tasks.score_task` | M8: heuristic quality scoring for every article/video |
| `app.tasks.pipeline_tasks.trend_task` | M11: burst detection (z-score of topic/entity mention frequency vs. trailing 30-day baseline) — LLM-free, pure SQL/statistics |
| `app.tasks.pipeline_tasks.stt_dispatch_task` | M12: claims queued `stt_jobs` rows (`queued`→`running`) and dispatches `transcribe_video_task` per job onto the `stt` queue |
| `app.tasks.pipeline_tasks.deep_video_task` | M12: chunks + chaptered-summarizes every video ≥ `LONG_VIDEO_THRESHOLD_SECONDS` (1200s) that doesn't have `content_chunks` yet — map via `ChunkSummaryAgent`, reduce via the existing `EnrichmentAgent` fed the concatenated chunk summaries |
| `app.tasks.stt_tasks.transcribe_video_task` | M12: yt-dlp audio pull + `faster-whisper` transcription for one caption-less video — routed to the `stt` queue only |
| `app.tasks.pipeline_tasks.run_full_pipeline_task` | scrape → stt-dispatch → embed → enrich/digest → deep-video → cluster → score → trends, what beat schedules |
| `app.tasks.affinity_tasks.aggregate_affinities_task` | Nightly (M7, extended M9): raw `user_events` → time-decayed `user_affinities` across source/topic/entity dimensions, then prunes events >90 days old via a `manage.py prune_old_events` subprocess |
| `app.tasks.profile_vector_tasks.compute_profile_vectors_task` | M9: nightly decayed weighted-mean embedding per user (`user_profile_vectors`) from click/save/digest_click events |
| `app.tasks.ranking_tasks.rank_all_users_task` | M9: the two-stage deterministic ranker, on its own 3-hour schedule — decoupled from digest cadence so `/feed` stays fresh |
| `app.tasks.search_tasks.embed_query_task` | M9: embeds a free-text search query — routed to the `interactive` queue only |
| `app.tasks.rag_tasks.rag_answer_task` | M14: full RAG chat turn — condense → embed → pgvector retrieval over `rag_chunks` → access-control filter → assemble numbered sources → Groq `llama-3.3-70b-versatile` (temp 0.3, max_tokens 700) → server-side citation validation. Routed to the `interactive` queue |
| `app.tasks.rag_tasks.rag_retrieve_task` | M14 Phase D: retrieval **only** (stops before generation) — returns a ready `system_prompt` + `handle_to_citation` so Django's SSE endpoint can open its own Groq stream. Routed to the `interactive` queue |
| `app.tasks.source_submission_tasks.evaluate_and_register_source_task` | M10: runs the AI-relevance gate against a user-submitted feed and registers it if accepted — routed to the `interactive` queue (a user is waiting live for the result) |
| `app.tasks.source_revalidation_tasks.revalidate_user_sources_task` | M10: monthly re-check of every user-submitted source against the same relevance gate — deactivates newly off-topic sources, reactivates previously-rejected ones that are relevant again |
| `app.tasks.trend_tasks.generate_weekly_trend_report_task` | M11: the weekly grounded, cited trend narrative (Pro) — retrieval-grounded LLM call with handle-based citation resolution, auto-publishes, emails effective-Pro users |

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

**⚠️ If your shell also runs `manage.py` from the root `.venv`** (e.g. an
activated `(ai-news-aggregator)` prompt, even while `cd`'d into `web/`) —
this machine has TWO Python environments capable of running Django, and a
package installed into only one of them will crash the OTHER one with
`ModuleNotFoundError` the moment you try to use it from there. Check which
one your shell actually uses (`python -c "import django; print(django.__file__)"`)
and mirror every `web/requirements.txt` install into it too — the root venv
is `uv`-managed (no standalone `pip.exe`), so use `uv pip install <pkg>`
there instead of a bare `pip install`. See `.wolf/cerebrum.md` and buglog
`web-020` for the exact incident this note exists to prevent.

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
python -m app.database.create_tables         # pgvector extension + 23 tables + stamps Alembic head
python -m app.database.seed_sources          # Source Registry (11 rows)
python -m app.database.seed_taxonomy_topics  # 27 taxonomy topics (M8)
cd web && .venv/Scripts/python.exe manage.py migrate && cd ..
cd web && .venv/Scripts/python.exe manage.py createsuperuser && cd ..   # optional
```

**Step 3 — Django development server** (required for the JSON API, auth, and chat)

```bash
cd web
.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
```

→ http://127.0.0.1:8000 (API + admin). The **UI** is served by Next.js — see Step 4.

**Step 4 — Next.js frontend** (required to actually use the app)

```bash
cd frontend
npm run dev            # http://localhost:3000
```

`frontend/next.config.ts` proxies `/api`, `/admin`, `/accounts`, `/behavior`,
`/assistant`, `/healthz`, `/r`, and `/static` to `http://127.0.0.1:8000` via
Next.js `rewrites()` — the dev-mode equivalent of what Caddy does in production.
**Browse the app at http://localhost:3000, not :8000.**

**Step 5 — Celery worker, default queue** (required for scheduled scrape/enrich/rank/digest — NOT required just to browse)

```bash
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info
```

**Step 6 — Interactive worker** (required for semantic search, **RAG chat**, and add-a-source)

```bash
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h
```

Without this: `/search` degrades to keyword search; **RAG chat returns 503**;
"add a source" times out.

**Step 7 — STT worker** (optional — only for videos whose captions are unavailable)

```bash
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q stt -n stt-worker@%h
```

**Step 8 — Celery beat** (required only if you want the schedules to fire automatically)

```bash
python -m celery -A app.celery_app:celery_app beat --loglevel=info
```

**Step 9 — Pipeline CLI** (on-demand, whenever you want fresh content or to force a phase)

```bash
python run_pipeline.py                    # full run, all 9 phases
python run_pipeline.py --skip-scraping    # re-process what's already in the DB
```

That's a fully running system: Postgres + Redis + pgAdmin in Docker, Django
serving the API, Next.js serving the UI, three Celery workers, beat firing the
schedule, and the pipeline CLI available on demand.

---

### 2. Recommended Terminal Layout

| Terminal | Runs | Required? |
|---|---|---|
| 1 | Docker (`up -d`, then leave it — or just check `ps` occasionally) | Required once |
| 2 | Django dev server (`:8000`) | Required — serves the whole API |
| 3 | Next.js dev server (`:3000`) | Required to see the UI |
| 4 | Celery worker (default queue) | Required for scheduled/background jobs; not needed if you only trigger things manually |
| 5 | Celery worker (**interactive** queue) | Required for semantic search, **RAG chat**, and add-a-source |
| 6 | Celery worker (**stt** queue) | Only for caption-less videos; everything else works without it |
| 7 | Celery beat | Required only for schedules to fire automatically — never required for manual/dev work |
| 8 | Manual pipeline runs, `manage.py shell`, ad-hoc debugging | Optional, as-needed |

**Minimum viable dev loop** (browse the site + trigger things manually, no
background automation): Terminals **1, 2, and 3** only, running
`python run_pipeline.py` by hand in a spare terminal whenever you want new content.

**Add Terminal 5** the moment you want to demo semantic search or the chatbot.

**Full production-like loop**: all 8.

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

**Table ownership map** (verified against the actual model files, M13):

| Owner | Tables | Migrated by |
|---|---|---|
| Pipeline (SQLAlchemy) | `articles`, `youtube_videos`, `embeddings`, **`rag_chunks`** (M14), `sources`, `user_rankings`, `digest_log`, `user_affinities`, `digest_click_tokens`, `taxonomy_topics`, `content_topics`, `entities`, `content_entities`, `content_clusters`, `content_cluster_members`, `content_enrichment`, `content_scores`, `user_profile_vectors`, `person_entities`, `trends`, `trend_reports`, `content_chunks`, `stt_jobs` — **23 tables** | Alembic |
| Django | `users` (+ `email_verified`), `user_profiles`, `personas`, `interests`, `user_interests`, `user_digest_settings`, `user_exclusions`, `user_events`, `saved_items`, `user_follows`, `user_source_subscriptions`, `stripe_customers`, **`chat_conversations`**, **`chat_messages`** (M14) | Django migrations |

**The two vector tables — know the difference:**

| | `embeddings` | `rag_chunks` |
|---|---|---|
| Rows per item | exactly **1** (unique on `content_type,content_id`) | **many** (one per passage) |
| Text embedded | `summary` → `content[:2000]` → `title` | the **original body / transcript**, chunked (~180 tok, 40 overlap) |
| Written by | `run_embedding_phase` + `DigestService._reembed` | `run_rag_index_phase` |
| Read by | clustering, ranking candidate generation, Django semantic search, relevance gate, profile vectors | **RAG retrieval only** |
| ANN index | **none** (exact scan) | **HNSW, `vector_cosine_ops`** |

Both use the same model and the same space (`all-MiniLM-L6-v2`, **384 dims**,
normalized) — `rag_chunks` imports `EMBEDDING_DIM` from `embedding.py` so they
can never drift.

M13 is the first milestone with **zero pipeline/Alembic schema change** — Stripe
customer/subscription mapping (`stripe_customers`) and `email_verified` are
both Django-owned per its own spec, and the ops dashboard reuses the
already-existing `apps.catalog.models.Source` mirror rather than adding
anything new pipeline-side.

**Read-only mirrors** (same physical table, read from the *other* ORM,
never migrated or written by it):

- Django reads pipeline tables via `web/apps/catalog/models.py`
  (`managed = False`) — all 22 pipeline tables above **except**
  `user_profile_vectors` (no Django mirror exists yet; only the pipeline
  reads it today). M12's `content_chunks`/`stt_jobs` mirrors follow the
  exact same pattern.
- The pipeline reads Django tables via
  `app/database/models/django_readmodels.py` (a separate `DjangoBase`) —
  all 11 Django tables above **except** `saved_items` (nothing in the
  pipeline needs it yet). M11 extended the `users` mirror (`DjangoUser`)
  with `plan`/`plan_expires_at` so the weekly trend-narrative broadcast
  email (run from the pipeline process) can identify effective-Pro users
  without importing Django.

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

- **`celery`** (default) — scrape, STT dispatch, embed, enrich, digest,
  deep-video chaptering, RAG passage indexing, cluster, score, trends
  (M11 burst detection), nightly affinity aggregation, nightly
  profile-vector computation, ranking, the monthly user-source
  re-validation job, and the weekly trend-narrative report. One
  worker process, `--pool=solo`.
- **`interactive`** (M9, extended M10 + M14) — `search_tasks.embed_query_task`,
  **`rag_tasks.rag_answer_task`**, **`rag_tasks.rag_retrieve_task`**, and
  `source_submission_tasks.evaluate_and_register_source_task`. A
  SEPARATE worker process, so a search request, a chat message, or an
  "add a source" submission never queues behind a multi-minute pipeline
  run on the default queue.
- **`stt`** (M12) — `stt_tasks.transcribe_video_task` only (yt-dlp audio pull +
  `faster-whisper` CPU transcription, minutes per video). Its own worker so it
  never blocks either of the other two queues. Ideally runs from a
  **residential IP** — yt-dlp is more likely to be blocked from a datacenter IP.

Routing is declared in `app/celery_app.py::task_routes` with module wildcards
(`app.tasks.search_tasks.*`, `app.tasks.rag_tasks.*`,
`app.tasks.source_submission_tasks.*` → `interactive`; `app.tasks.stt_tasks.*`
→ `stt`). That wildcard is exactly why `source_revalidation_tasks` is a
**separate module** from `source_submission_tasks` — it shares the same
relevance gate but is a batch job that belongs on the default queue.

**Scheduled jobs** (Celery beat — all crontab, code-defined in
`app/celery_app.py`, no DB-backed schedule table):

| Job | Schedule | Type |
|---|---|---|
| `run_full_pipeline_task` | every 6h | batch |
| `aggregate_affinities_task` | nightly, 3:00 UTC | nightly batch |
| `compute_profile_vectors_task` | nightly, 3:15 UTC | nightly batch |
| `rank_all_users_task` | every 3h | periodic batch |
| `revalidate_user_sources_task` | monthly, 1st @ 4:00 UTC | periodic batch |
| `generate_weekly_trend_report_task` | weekly, Monday @ 6:00 UTC | periodic, LLM-driven |

**Interactive (request-time) jobs**: `embed_query_task` and (M10)
`evaluate_and_register_source_task` — a user waits live for both. Everything
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

**STT fails** (`transcribe_video_task` errors, or `yt-dlp`/`ffmpeg` not found)
→ `ffmpeg` must be on `PATH` (yt-dlp shells out to it for audio extraction) —
`ffmpeg -version` should print a real version. First run downloads the
`WHISPER_MODEL` (default `distil-large-v3`, ~1.5GB) from Hugging Face; expect
a one-time delay. Check `stt_jobs.error_message` for the specific failure
(`SttJobRepository.get_for_content(...)`) — a video that's genuinely
unavailable/region-locked/deleted on YouTube will fail here, not silently.

**New `templatetags/*.py` file throws `TemplateSyntaxError: 'X' is not a
registered tag library`**
→ The dev server was already running before the new file existed — Django's
tag-library registry is built once at process startup and doesn't reliably
pick up a brand-new templatetags module via the normal autoreloader. Restart
the dev server. See buglog `web-014`.

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
- [ ] (M13) Register a test account → console-backend email shows a real
      verification link → clicking it flips `email_verified` → the SAME
      link clicking again is rejected ("invalid or already used")
- [ ] (M13) `/ops/` returns 403 for a non-staff user, 200 for `is_staff=True`
- [ ] (M13) `/pricing/` and `/accounts/billing/` render correctly for both
      a Free and a Pro user; the "Upgrade to Pro" button is disabled
      whenever `STRIPE_SECRET_KEY`/`STRIPE_PRICE_ID_PRO` are unset

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

### Testing the Stripe webhook without a real Stripe account (M13)
- `STRIPE_WEBHOOK_SECRET` just needs to match on both sides — it doesn't have
  to come from a real Stripe dashboard/CLI. Set any string in `web/.env`
  (e.g. `whsec_local_dev_test_only...`), then hand-construct a signed test
  event in a Django shell:
  ```python
  import stripe, json, time
  payload = json.dumps({"id": "evt_test", "object": "event", "type": "checkout.session.completed",
                         "data": {"object": {"client_reference_id": "1", "customer": "cus_x", "subscription": "sub_x"}}})
  ts = int(time.time())
  sig = stripe.WebhookSignature._compute_signature(f"{ts}.{payload}", "whsec_local_dev_test_only...")
  # POST payload to /accounts/stripe/webhook/ with header Stripe-Signature: f"t={ts},v1={sig}"
  ```
  This exercises the real signature-verification + event-handling code path
  with zero network calls to Stripe — only `stripe.checkout.Session.create()`
  (an actual outbound API call) needs real `STRIPE_SECRET_KEY`/`STRIPE_PRICE_ID_PRO`.
- `stripe.Webhook.construct_event()` returns a `StripeObject`, not a plain
  dict — call `.to_dict()` before handing it to `.get()`-based handler code
  (see buglog `web-015`).

---

## Production Deployment Checklist

- [ ] Change all default passwords in `.env` / `.env.prod` / `web/.env.prod`
- [ ] Point `DATABASE_URL` at the managed Postgres (Neon) endpoint — the prod
      compose file has **no `db` service** on purpose
- [ ] Remove the `pgadmin` service from docker-compose.yml
- [ ] Never ship `POSTGRES_HOST_AUTH_METHOD: trust` (dev compose only)
- [ ] Set `LOG_LEVEL=WARNING` in the production `.env`
- [ ] `DJANGO_DEBUG=False`, real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
      and `DJANGO_CSRF_TRUSTED_ORIGINS` (full origins **with scheme**)
- [ ] Set `SITE_DOMAIN` in `docker/.env` so Caddy can request a Let's Encrypt cert
- [ ] Run the pipeline via Celery beat, not a raw cron entry — the manual
      `run_pipeline.py` CLI still works as a fallback for one-off runs
- [ ] Confirm `worker-interactive` is running, or search/chat/add-source break
- [ ] Add monitoring: alert if `run_pipeline.py` exits with code 1, **and**
      alert if beat stops firing — `run_full_pipeline_task` returns normally
      even when phases recorded errors, so the Celery path never surfaces failure

---

# Complete Command Reference

Everything you can run, grouped by what you're trying to do. Unless noted,
run from the **repository root** with the root `.venv` active.

## Docker services

```bash
# Start everything (dev): postgres, redis, worker-default, worker-stt, beat, pgadmin
docker compose -f docker/docker-compose.yml up -d

# Start only the datastores (recommended for local dev — run workers on the host)
docker compose -f docker/docker-compose.yml up -d db redis

# Status / logs / stop
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f db
docker compose -f docker/docker-compose.yml logs -f worker-default
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml down -v      # ALSO WIPES the volumes

# Rebuild the pipeline image after changing Dockerfile / pyproject.toml
docker compose -f docker/docker-compose.yml build --no-cache
docker compose -f docker/docker-compose.yml up -d --force-recreate worker-default

# Health checks
docker exec ai_news_redis redis-cli ping                 # -> PONG
docker exec ai_news_db pg_isready -U ai_news_user -d ai_news
```

## Production stack

```bash
docker compose -f docker/docker-compose.prod.yml up -d --build
docker compose -f docker/docker-compose.prod.yml ps
docker compose -f docker/docker-compose.prod.yml logs -f web
docker compose -f docker/docker-compose.prod.yml logs -f worker-interactive
docker compose -f docker/docker-compose.prod.yml logs -f caddy
docker compose -f docker/docker-compose.prod.yml restart worker-default
docker compose -f docker/docker-compose.prod.yml down
```

## Database initialisation & seeding

```bash
python -m app.database.create_tables            # extension + 23 tables + alembic stamp head
python -m app.database.seed_sources             # Source Registry, 11 rows, idempotent
python -m app.database.seed_taxonomy_topics     # ~27 taxonomy topics, idempotent
```

## Backfills (deliberate, one-off)

```bash
# Enrichment for pre-M8 rows (they have summaries but no content_enrichment row)
python -m app.database.backfill_enrichment --limit 50 --provider local   # Ollama, $0
python -m app.database.backfill_enrichment --provider groq                # full corpus, Groq
python -m app.database.backfill_enrichment --limit 100 --version v1-backfill-ollama

# transcript_segments for videos scraped before M12
python -m app.database.backfill_transcript_segments
```

## The pipeline CLI

```bash
python run_pipeline.py                              # full run — all 9 phases
python run_pipeline.py --hours 48                   # override the 144h default lookback
python run_pipeline.py --dry-run                    # scrape + validate ONLY, write nothing
python run_pipeline.py --skip-scraping              # re-process what's already in the DB
python run_pipeline.py --skip-digest                # scrape/embed, but no enrichment or email
python run_pipeline.py --skip-email                 # build the digest, print it instead of sending
python run_pipeline.py --skip-scraping --skip-email  # fastest full re-process loop

# --source accepts 'all', 'blogs', 'youtube', or ANY active Source Registry key.
# Pass an invalid value to have the current valid keys printed back at you.
python run_pipeline.py --source youtube --skip-digest
python run_pipeline.py --source blogs
python run_pipeline.py --source arxiv
python run_pipeline.py --source reddit
python run_pipeline.py --source github_release
python run_pipeline.py --source government_us
python run_pipeline.py --source government_uk
python run_pipeline.py --source government_nist
python run_pipeline.py --source funding_crunchbase
python run_pipeline.py --source huggingface_model
python run_pipeline.py --help
```

Exit code **1** means at least one error was recorded (scraper, DB insert,
digest, scoring, or RAG indexing) — that's the alerting hook.

## Celery — workers, beat, and one-off dispatch

```bash
# ALWAYS `python -m celery`, never bare `celery`, ALWAYS from the repo root.
# --pool=solo because Celery's prefork pool misbehaves on Windows.

# Default queue (the 6-hourly pipeline, ranking, affinities, profile vectors, trends)
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info

# Interactive queue (semantic search, RAG chat, add-a-source)
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q interactive -n interactive-worker@%h

# STT queue (caption-less video transcription)
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info -Q stt -n stt-worker@%h

# Beat (the scheduler — publishes, never executes)
python -m celery -A app.celery_app:celery_app beat --loglevel=info

# Inspection
python -c "from app.celery_app import celery_app; print(celery_app.control.ping(timeout=2.0))"
python -m celery -A app.celery_app:celery_app inspect active
python -m celery -A app.celery_app:celery_app inspect registered
python -m celery -A app.celery_app:celery_app inspect scheduled
python -m celery -A app.celery_app:celery_app purge          # DESTRUCTIVE: drop all queued messages
```

### Trigger any task by hand

`.run()` executes **inline in the current process** (no worker needed).
`.delay()` dispatches **through Redis** (needs a worker on the right queue).

```bash
# Health round-trip
python -c "from app.tasks.health_tasks import ping_task; print(ping_task.delay('hi').get(timeout=10))"

# Whole pipeline
python -c "from app.tasks.pipeline_tasks import run_full_pipeline_task; print(run_full_pipeline_task.run())"

# Individual phases
python -c "from app.tasks.pipeline_tasks import scrape_task;       print(scrape_task.run('all', 144))"
python -c "from app.tasks.pipeline_tasks import stt_dispatch_task; print(stt_dispatch_task.run())"
python -c "from app.tasks.pipeline_tasks import embed_task;        print(embed_task.run())"
python -c "from app.tasks.pipeline_tasks import digest_task;       print(digest_task.run(144, True))"   # skip_email=True
python -c "from app.tasks.pipeline_tasks import deep_video_task;   print(deep_video_task.run())"
python -c "from app.tasks.pipeline_tasks import rag_index_task;    print(rag_index_task.run())"
python -c "from app.tasks.pipeline_tasks import cluster_task;      print(cluster_task.run())"
python -c "from app.tasks.pipeline_tasks import score_task;        print(score_task.run())"
python -c "from app.tasks.pipeline_tasks import trend_task;        print(trend_task.run())"

# Personalization
python -c "from app.tasks.ranking_tasks import rank_all_users_task;              print(rank_all_users_task.run())"
python -c "from app.tasks.affinity_tasks import aggregate_affinities_task;       print(aggregate_affinities_task.run())"
python -c "from app.tasks.profile_vector_tasks import compute_profile_vectors_task; print(compute_profile_vectors_task.run())"

# Sources & trends
python -c "from app.tasks.source_revalidation_tasks import revalidate_user_sources_task; print(revalidate_user_sources_task.run())"
python -c "from app.tasks.trend_tasks import generate_weekly_trend_report_task;  print(generate_weekly_trend_report_task.run())"

# STT for one specific video (by youtube_videos.id)
python -c "from app.tasks.stt_tasks import transcribe_video_task; print(transcribe_video_task.run(content_id=123))"
```

## Smoke-test the AI components directly (no Celery, no web server)

```bash
# Embedding model — should print 384
python -c "from app.embeddings.embedding_service import embed_text; print(len(embed_text('test query')))"

# RAG chunker — passages from a string
python -c "from app.rag.chunker import chunk_article; ps=chunk_article('Sentence one. '*200); print(len(ps), ps[0].token_count, ps[0].char_start, ps[0].char_end)"

# Full RAG answer end-to-end (needs GROQ_API_KEY + an indexed corpus)
python -c "from app.database import get_db_session; from app.services.rag_service import answer_question; \
import json; \
db_ctx=get_db_session(); db=db_ctx.__enter__(); \
print(json.dumps(answer_question(db, 'What is new in AI agents?'), indent=2)[:2000])"

# Retrieval only (no generation, no Groq key needed)
python -c "from app.database import get_db_session; from app.services.rag_service import retrieve_context; \
db_ctx=get_db_session(); db=db_ctx.__enter__(); \
r=retrieve_context(db, 'AI regulation'); print(r.mode, r.has_results, list(r.handle_to_citation))"

# Enrichment on a made-up article (1 real LLM call)
python -c "from app.agents.enrichment_agent import EnrichmentAgent; \
a=EnrichmentAgent(allowed_topics={'llms','ai-agents'}); \
print(a.generate('OpenAI ships a new model', 'OpenAI today announced a new frontier model with native tool use. '*20))"

# Relevance gate against any feed URL
python -c "from app.database import get_db_session; from app.services.relevance_gate import evaluate_source; \
db_ctx=get_db_session(); db=db_ctx.__enter__(); \
r=evaluate_source('https://news.crunchbase.com/sections/ai/feed/', db); print(r.decision, round(r.score,3), r.message)"

# Ranking evaluation (NDCG@10 + MAP) for every user with a stored ranking
python -c "from app.database import get_db_session; from app.eval.ranking_eval import evaluate_all_users; \
db_ctx=get_db_session(); db=db_ctx.__enter__(); print(evaluate_all_users(db))"
```

## Django

```bash
cd web

.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py makemigrations
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run   # CI drift check
.venv/Scripts/python.exe manage.py sqlmigrate onboarding 0005          # preview SQL
.venv/Scripts/python.exe manage.py createsuperuser
.venv/Scripts/python.exe manage.py shell
.venv/Scripts/python.exe manage.py dbshell                              # needs a local psql
.venv/Scripts/python.exe manage.py prune_old_events                     # manual retention prune
.venv/Scripts/python.exe manage.py collectstatic                        # PRODUCTION ONLY

cd ..
```

## Frontend

```bash
cd frontend

npm install
npm run dev            # http://localhost:3000 — proxies API paths to :8000
npm run build          # next build + copies static/public into .next/standalone
npm run start          # serve the standalone production build
npm run lint

cd ..
```

## Alembic (pipeline migrations only — never Django tables)

```bash
alembic current                                          # what revision is this DB on
alembic history                                          # full revision chain
alembic check                                            # verify zero model/schema drift
alembic revision --autogenerate -m "add some_column"     # ALWAYS review the generated file
alembic upgrade head
alembic downgrade -1
alembic stamp head                                       # baseline an existing DB, no DDL
```

> If a new migration adds the **first** pgvector `Vector` column in that file,
> add `import pgvector.sqlalchemy` by hand — autogenerate does not emit it.

## Database exploration

```bash
# psql inside the container (no local psql needed)
docker exec -it ai_news_db psql -U ai_news_user -d ai_news

# One-off queries from the shell
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT count(*) FROM articles;"
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT count(*) FROM embeddings;"
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT count(*) FROM rag_chunks;"
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT source, count(*) FROM articles GROUP BY source ORDER BY 2 DESC;"
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT count(*) FROM content_clusters;"
docker exec ai_news_db psql -U ai_news_user -d ai_news -c "SELECT status, count(*) FROM stt_jobs GROUP BY status;"

# Backup / restore
docker exec ai_news_db pg_dump -U ai_news_user -d ai_news -Fc > backup.dump
docker exec -i ai_news_db pg_restore -U ai_news_user -d ai_news --clean < backup.dump
```

Useful health queries:

```sql
-- Is the corpus enriched?
SELECT (SELECT count(*) FROM articles) AS articles,
       (SELECT count(*) FROM content_enrichment WHERE content_type='article') AS enriched,
       (SELECT count(*) FROM embeddings) AS embeddings,
       (SELECT count(*) FROM rag_chunks) AS rag_passages;

-- Source Registry health
SELECT key, is_active, visibility, last_run_at, last_success_at FROM sources ORDER BY key;

-- Clusters with 2+ members (the ones that actually exist — singletons are discarded)
SELECT cluster_id, count(*) FROM content_cluster_members GROUP BY cluster_id ORDER BY 2 DESC LIMIT 10;

-- What's trending right now
SELECT dimension, key, mention_count, round(z_score::numeric,2) AS z
FROM trends WHERE date = (SELECT max(date) FROM trends) AND is_trending ORDER BY z_score DESC;

-- One user's ranking, with the winning explanation
SELECT rank, content_type, content_id, relevance_score, reasoning
FROM user_rankings WHERE user_id = 1 ORDER BY rank;

-- Chat activity
SELECT c.id, c.scope_type, count(m.id) AS msgs, max(m.created_at) AS last
FROM chat_conversations c LEFT JOIN chat_messages m ON m.conversation_id = c.id
GROUP BY c.id ORDER BY last DESC NULLS LAST LIMIT 10;
```

## Tests

```bash
pytest                                                  # full suite
pytest -v
pytest tests/test_database.py -v                        # in-memory SQLite, no Postgres needed
pytest tests/test_feed_ranking.py -v                    # pure-function home diversification
pytest tests/test_scrapers.py -v                        # ⚠ makes REAL network calls
pytest -k "ranking"                                     # filter by keyword
pytest tests/ --cov=app --cov-report=term-missing
```

> Known baseline: **14 passed, 22 pre-existing errors.** The errors are the
> SQLite/JSONB/Vector incompatibility in `test_database.py` — SQLite can't
> create the pgvector and JSONB columns. Any *other* failure count is a real
> regression.

## API smoke tests (curl)

```bash
curl -s http://127.0.0.1:8000/healthz/                                  # {"status":"ok"}
curl -s "http://127.0.0.1:8000/api/news/home/?limit=5" | head -c 500
curl -s "http://127.0.0.1:8000/api/news/search/?q=agents" | head -c 500
curl -s "http://127.0.0.1:8000/api/news/clusters/?hours=168" | head -c 500

# Authenticated endpoints need a session cookie + CSRF token — easiest from the
# browser devtools console on http://localhost:3000, or:
curl -s -c cookies.txt http://127.0.0.1:8000/api/session/
```

## Restarting after code changes

```bash
# Celery workers do NOT hot-reload. After editing anything under app/ that a
# task imports, Ctrl+C the worker and start it again — a running worker keeps
# executing the OLD code silently.

# Django runserver DOES auto-reload, EXCEPT for brand-new templatetags modules
# (restart it manually in that case).

# Next.js dev server hot-reloads.
```

---