# run_pipeline.py
#
# This is the main entry point for the full data pipeline.
#
# What it does, in order:
#   1.  Load config + validate DB connection
#   2.  Scrape YouTube transcripts
#   3.  Scrape OpenAI + Anthropic blog articles
#   4.  Insert all results into PostgreSQL (duplicates are silently skipped)
#   5.  Print a summary of what was inserted
#
# Usage:
#   python run_pipeline.py
#   python run_pipeline.py --hours 48        # override lookback window
#   python run_pipeline.py --source youtube  # only run YouTube scraper
#   python run_pipeline.py --source blogs    # only run blog scraper
#   python run_pipeline.py --dry-run         # scrape but do NOT write to DB

import argparse
import logging
import sys
import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# Load .env BEFORE any other project imports that read env vars
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result summary dataclass
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PipelineResult:
    youtube_scraped:   int = 0
    youtube_inserted:  int = 0
    youtube_skipped:   int = 0
    youtube_errors:    int = 0

    articles_scraped:  int = 0
    articles_inserted: int = 0
    articles_skipped:  int = 0
    articles_errors:   int = 0

    def print_summary(self) -> None:
        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(
            f"  YouTube  : scraped={self.youtube_scraped:>4}  "
            f"inserted={self.youtube_inserted:>4}  "
            f"skipped={self.youtube_skipped:>4}  "
            f"errors={self.youtube_errors:>4}"
        )
        logger.info(
            f"  Articles : scraped={self.articles_scraped:>4}  "
            f"inserted={self.articles_inserted:>4}  "
            f"skipped={self.articles_skipped:>4}  "
            f"errors={self.articles_errors:>4}"
        )
        total_scraped   = self.youtube_scraped   + self.articles_scraped
        total_inserted  = self.youtube_inserted  + self.articles_inserted
        total_skipped   = self.youtube_skipped   + self.articles_skipped
        logger.info(
            f"  TOTAL    : scraped={total_scraped:>4}  "
            f"inserted={total_inserted:>4}  "
            f"skipped={total_skipped:>4}"
        )
        logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate_scraped_article(item) -> List[str]:
    """
    Lightweight validation before we attempt to insert into the DB.
    Returns a list of error strings (empty list = valid).
    """
    errors = []
    if not item.title or not item.title.strip():
        errors.append("missing title")
    if not item.url or not item.url.startswith("http"):
        errors.append(f"invalid url: {item.url!r}")
    if not item.content or len(item.content.strip()) < 50:
        errors.append("content too short (< 50 chars)")
    if item.published_at is None:
        errors.append("missing published_at")
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Phase runners
# ─────────────────────────────────────────────────────────────────────────────

def run_youtube_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    from app.scrapers.youtube_scraper import YouTubeScraper
    from app.database import get_db_session, YoutubeRepository

    logger.info(f"[YouTube] Starting scrape  (hours_lookback={hours})")
    try:
        scraper = YouTubeScraper()
        items   = scraper.scrape(hours_lookback=hours)
    except Exception as exc:
        logger.error(f"[YouTube] Scraper crashed: {exc}", exc_info=True)
        result.youtube_errors += 1
        return

    result.youtube_scraped = len(items)
    logger.info(f"[YouTube] Scraped {len(items)} items")

    # Validate
    valid_items = []
    for item in items:
        errors = _validate_scraped_article(item)
        if errors:
            logger.warning(f"[YouTube] Skipping invalid item '{item.title}': {errors}")
            result.youtube_errors += 1
        else:
            valid_items.append(item)

    if dry_run:
        logger.info(f"[YouTube] DRY RUN — would insert {len(valid_items)} items")
        return

    if not valid_items:
        logger.info("[YouTube] Nothing valid to insert")
        return

    try:
        with get_db_session() as db:
            repo     = YoutubeRepository(db)
            inserted, skipped = repo.bulk_create(valid_items)
            result.youtube_inserted = inserted
            result.youtube_skipped  = skipped
    except Exception as exc:
        logger.error(f"[YouTube] DB insertion failed: {exc}", exc_info=True)
        result.youtube_errors += 1


def run_blogs_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    from app.scrapers.blog_scraper import BlogScraper
    from app.database import get_db_session, ArticleRepository

    logger.info(f"[Blogs] Starting scrape  (hours_lookback={hours})")
    try:
        scraper = BlogScraper()
        items   = scraper.scrape(hours_lookback=hours)
    except Exception as exc:
        logger.error(f"[Blogs] Scraper crashed: {exc}", exc_info=True)
        result.articles_errors += 1
        return

    result.articles_scraped = len(items)
    logger.info(f"[Blogs] Scraped {len(items)} items")

    # Validate
    valid_items = []
    for item in items:
        errors = _validate_scraped_article(item)
        if errors:
            logger.warning(f"[Blogs] Skipping invalid item '{item.title}': {errors}")
            result.articles_errors += 1
        else:
            valid_items.append(item)

    if dry_run:
        logger.info(f"[Blogs] DRY RUN — would insert {len(valid_items)} items")
        return

    if not valid_items:
        logger.info("[Blogs] Nothing valid to insert")
        return

    try:
        with get_db_session() as db:
            repo     = ArticleRepository(db)
            inserted, skipped = repo.bulk_create(valid_items)
            result.articles_inserted = inserted
            result.articles_skipped  = skipped
    except Exception as exc:
        logger.error(f"[Blogs] DB insertion failed: {exc}", exc_info=True)
        result.articles_errors += 1


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Aggregator Pipeline")
    parser.add_argument(
        "--hours",
        type=int,
        default=int(os.getenv("HOURS_LOOKBACK", "144")),
        help="How many hours back to scrape (default: 144 = 6 days)",
    )
    parser.add_argument(
        "--source",
        choices=["all", "youtube", "blogs"],
        default="all",
        help="Which scraper(s) to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape but do NOT write to the database",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AI NEWS AGGREGATOR — PIPELINE START")
    logger.info(f"  hours={args.hours}  source={args.source}  dry_run={args.dry_run}")
    logger.info("=" * 60)

    # ── Step 1: check DB connection (skip in dry-run mode) ────────────────
    if not args.dry_run:
        from app.database.session import check_database_connection
        if not check_database_connection():
            logger.error(
                "Cannot reach PostgreSQL. Start it with:\n"
                "  docker compose -f docker/docker-compose.yml up -d\n"
                "Then initialise tables:\n"
                "  python -m app.database.create_tables"
            )
            sys.exit(1)

    result = PipelineResult()

    # ── Step 2: run scrapers ───────────────────────────────────────────────
    if args.source in ("all", "youtube"):
        run_youtube_phase(args.hours, args.dry_run, result)

    if args.source in ("all", "blogs"):
        run_blogs_phase(args.hours, args.dry_run, result)

    # ── Step 3: summary ───────────────────────────────────────────────────
    result.print_summary()

    # Exit with non-zero code if there were errors (useful for CI/cron alerting)
    total_errors = result.youtube_errors + result.articles_errors
    if total_errors > 0:
        logger.warning(f"Pipeline completed with {total_errors} error(s)")
        sys.exit(1)

    logger.info("Pipeline completed successfully.")


if __name__ == "__main__":
    main()