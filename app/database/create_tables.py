# app/database/create_tables.py
#
# Run this ONCE after starting PostgreSQL to create all tables.
# Safe to re-run — SQLAlchemy uses CREATE TABLE IF NOT EXISTS under the hood.
#
# Usage:
#   python -m app.database.create_tables

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def create_all_tables() -> None:
    """
    Import every model (so SQLAlchemy knows about them), then call
    Base.metadata.create_all() which issues CREATE TABLE IF NOT EXISTS
    for every registered model.
    """
    from app.database.base import Base
    from app.database.session import engine, check_database_connection

    # Step 1: verify we can actually reach the database
    logger.info("Checking database connection...")
    if not check_database_connection():
        logger.error(
            "Cannot connect to PostgreSQL. "
            "Make sure Docker is running:  docker compose -f docker/docker-compose.yml up -d"
        )
        sys.exit(1)

    # Step 1.5: enable the pgvector extension (one-time, safe to re-run)
    logger.info("Enabling pgvector extension...")
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    logger.info("pgvector extension enabled")
    
    # Step 2: import ALL models so they register themselves with Base.metadata.
    # If you add a new model file, add its import here.
    logger.info("Loading models...")
    from app.database.models import (  # noqa: F401
        Article, YoutubeVideo, Embedding, Source, UserRanking, DigestLog,
        UserAffinity, DigestClickToken,
        TaxonomyTopic, ContentTopic, Entity, ContentEntity,
        ContentCluster, ContentClusterMember, ContentEnrichment, ContentScore,
    )

    # Step 3: create tables
    logger.info("Creating tables (CREATE TABLE IF NOT EXISTS)...")
    Base.metadata.create_all(bind=engine)

    # Step 4: report what was created
    table_names = list(Base.metadata.tables.keys())
    logger.info(f"Tables available: {table_names}")

    # Step 5: mark this DB as Alembic-current. A brand-new DB created here has
    # no alembic_version row; without this, a later `alembic upgrade head`
    # would try to replay the baseline migration's CREATE TABLEs against
    # tables that already exist and fail. Stamping (not upgrading) keeps a
    # fresh DB and an existing hand-migrated DB on the identical Alembic state.
    # This MUST be the last step: alembic/env.py calls logging.fileConfig(),
    # which disables every logger configured above it (Python logging's
    # default fileConfig behavior) — any logger.info() after this point would
    # silently vanish, confirmed live. Use print() for the final line instead.
    logger.info("Stamping Alembic head (schema changes go through migrations from here on)...")
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.stamp(alembic_cfg, "head")

    print("Done. Database is ready (schema + Alembic state both current).")


if __name__ == "__main__":
    create_all_tables()