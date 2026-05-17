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

    # Step 2: import ALL models so they register themselves with Base.metadata.
    # If you add a new model file, add its import here.
    logger.info("Loading models...")
    from app.database.models import Article, YoutubeVideo  # noqa: F401

    # Step 3: create tables
    logger.info("Creating tables (CREATE TABLE IF NOT EXISTS)...")
    Base.metadata.create_all(bind=engine)

    # Step 4: report what was created
    table_names = list(Base.metadata.tables.keys())
    logger.info(f"Tables available: {table_names}")
    logger.info("Done. Database is ready.")


if __name__ == "__main__":
    create_all_tables()