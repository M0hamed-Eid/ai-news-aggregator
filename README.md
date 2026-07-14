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
┌──────────▼────────────┐        ┌─────────────────┐
│  Redis (6379)          │◄──────►│  Celery worker  │  --pool=solo (Windows)
│  broker + result store │        │  app/tasks/*    │  runs scrape/embed/digest
└──────────┬─────────────┘        └─────────────────┘
           │ schedules
┌──────────▼─────────────┐
│  Celery beat            │  fires run_full_pipeline_task every 6h
│  (app/celery_app.py)    │  (crontab, no DB-backed schedule)
└──────────────────────────┘

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
# Terminal 1 — executes tasks
python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info

# Terminal 2 — fires the scheduled task every 6 hours (crontab, code-defined,
# no django-celery-beat / no DB-backed schedule table)
python -m celery -A app.celery_app:celery_app beat --loglevel=info
```

### Available tasks

| Task | Purpose |
|---|---|
| `app.tasks.health_tasks.ping_task` | Trivial round-trip check |
| `app.tasks.pipeline_tasks.scrape_task` | One source or "all" |
| `app.tasks.pipeline_tasks.embed_task` | Embed unembedded content |
| `app.tasks.pipeline_tasks.digest_task` | Rank + send digests |
| `app.tasks.pipeline_tasks.run_full_pipeline_task` | scrape → embed → digest, what beat schedules |

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