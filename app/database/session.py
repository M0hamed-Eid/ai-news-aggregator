# app/database/session.py
#
# This file is responsible for TWO things:
#   1. Creating the SQLAlchemy "engine" (the connection to PostgreSQL).
#   2. Providing a "session factory" that the rest of the app uses to
#      open database transactions.
#
# The key design choice here is "Session-per-operation":
#   - Every function that needs the DB calls  get_db_session()
#   - It opens a session, does its work, commits, and closes.
#   - This keeps transactions short and avoids connection leaks.

import logging
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

load_dotenv()  # read .env before anything else

logger = logging.getLogger(__name__)

# =============================================================================
# Build the DATABASE_URL
# =============================================================================
# Priority:
#   1. DATABASE_URL env var (explicit, good for CI/CD pipelines)
#   2. Individual POSTGRES_* vars (convenient for Docker / local dev)

def _build_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    user     = os.getenv("POSTGRES_USER",     "ai_news_user")
    password = os.getenv("POSTGRES_PASSWORD", "changeme_in_production")
    host     = os.getenv("POSTGRES_HOST",     "localhost")
    port     = os.getenv("POSTGRES_PORT",     "5432")
    dbname   = os.getenv("POSTGRES_DB",       "ai_news")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


DATABASE_URL = _build_database_url()

# =============================================================================
# Engine configuration
# =============================================================================
# QueuePool: maintains a pool of re-usable connections.
#   pool_size        — how many connections to keep open permanently
#   max_overflow     — extra connections allowed under heavy load
#   pool_timeout     — seconds to wait for a free connection before raising
#   pool_recycle     — recycle connections older than N seconds
#                      (prevents "server closed connection" after idle periods)
#   pool_pre_ping    — test each connection before using it (auto-heal after
#                      a network hiccup or a Postgres restart)

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,      # 30 minutes
    pool_pre_ping=True,
    echo=False,             # set True only during development to see SQL
)

# =============================================================================
# Session factory
# =============================================================================
# SessionLocal is a CLASS (a "factory"). Each call to SessionLocal() creates
# a NEW session object.
#
# autocommit=False  → you must call session.commit() explicitly.
# autoflush=False   → SQLAlchemy won't auto-flush pending changes before
#                     every query. This gives you full control.

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


# =============================================================================
# Context manager helper
# =============================================================================
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Usage (recommended pattern throughout the project):

        from app.database.session import get_db_session

        with get_db_session() as db:
            articles = db.query(Article).all()

    The context manager:
      - Opens a session
      - Yields it to your code
      - Commits on success
      - Rolls back on any exception (so the DB is never left in a broken state)
      - Always closes the session (releases the connection back to the pool)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database session error — rolled back: {exc}")
        raise
    finally:
        session.close()


# =============================================================================
# Health check
# =============================================================================
def check_database_connection() -> bool:
    """
    Returns True if we can reach PostgreSQL, False otherwise.
    Use this in a startup check or a /health endpoint.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection: OK")
        return True
    except Exception as exc:
        logger.error(f"Database connection: FAILED — {exc}")
        return False