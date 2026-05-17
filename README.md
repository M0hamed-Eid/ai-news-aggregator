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
- [ ] Schedule `run_pipeline.py` with cron or a task scheduler:
      `0 */6 * * * cd /app && python run_pipeline.py >> /var/log/pipeline.log 2>&1`
- [ ] Set up Alembic for schema migrations (when you add columns later):
      `alembic init alembic && alembic revision --autogenerate -m "init"`
- [ ] Add monitoring: alert if pipeline exits with code 1 (errors occurred)