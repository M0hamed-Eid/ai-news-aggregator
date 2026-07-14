# app/database/db_url.py
#
# Single source of truth for resolving the pipeline's Postgres URL.
#
# Shared by app/database/session.py (the running app) AND alembic/env.py
# (the migration tool) so the two can never independently drift on which
# database they point at — a migration tool that resolves the URL
# differently than the app itself is exactly the kind of divergence that
# causes a migration to silently run against the wrong database.

import os


def build_database_url() -> str:
    """
    Priority:
      1. DATABASE_URL env var (explicit, good for CI/CD pipelines)
      2. Individual POSTGRES_* vars (convenient for Docker / local dev)
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    user     = os.getenv("POSTGRES_USER",     "ai_news_user")
    password = os.getenv("POSTGRES_PASSWORD", "changeme_in_production")
    host     = os.getenv("POSTGRES_HOST",     "localhost")
    port     = os.getenv("POSTGRES_PORT",     "5432")
    dbname   = os.getenv("POSTGRES_DB",       "ai_news")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
