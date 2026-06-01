# run_pipeline.py
#
# Main entry point for the full data pipeline.
#
# Phase 1 — scrape YouTube + blogs → insert into PostgreSQL
# Phase 2 — generate AI summaries (DigestAgent) for unsummarised records
# Phase 3 — rank content (CuratorAgent) + build + send email (EmailAgent)
#
# Usage:
#   python run_pipeline.py
#   python run_pipeline.py --hours 48             # override lookback window
#   python run_pipeline.py --source youtube       # only YouTube scraper
#   python run_pipeline.py --source blogs         # only blog scraper
#   python run_pipeline.py --skip-scraping        # skip Phase 1, use existing DB content
#   python run_pipeline.py --skip-digest          # skip Phase 2+3
#   python run_pipeline.py --skip-email           # run digest but print instead of sending
#   python run_pipeline.py --dry-run              # scrape but do NOT write to DB
#
# Changes from previous version
# ----------------------------------
# 1. Added --skip-scraping CLI flag so Phase 1 can be bypassed when all
#    content is already in the DB (saves significant time during dev/testing).
# 2. Switched AI provider from OpenAI to Groq throughout.
#    OPENAI_API_KEY is no longer required; GROQ_API_KEY is used instead.

import argparse
import logging
import sys
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# ── Load .env BEFORE any project imports that read env vars ──────────────────
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result summary
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

    digest_articles_summarised: int = 0
    digest_videos_summarised:   int = 0
    digest_total_ranked:        int = 0
    digest_errors: List[str] = field(default_factory=list)

    def print_summary(self) -> None:
        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(
            "  YouTube  : scraped=%4d  inserted=%4d  skipped=%4d  errors=%4d",
            self.youtube_scraped, self.youtube_inserted,
            self.youtube_skipped, self.youtube_errors,
        )
        logger.info(
            "  Articles : scraped=%4d  inserted=%4d  skipped=%4d  errors=%4d",
            self.articles_scraped, self.articles_inserted,
            self.articles_skipped, self.articles_errors,
        )
        total_scraped  = self.youtube_scraped  + self.articles_scraped
        total_inserted = self.youtube_inserted + self.articles_inserted
        total_skipped  = self.youtube_skipped  + self.articles_skipped
        logger.info(
            "  TOTAL    : scraped=%4d  inserted=%4d  skipped=%4d",
            total_scraped, total_inserted, total_skipped,
        )
        if self.digest_articles_summarised or self.digest_videos_summarised:
            logger.info(
                "  Digest   : articles summarised=%4d  videos summarised=%4d  ranked=%4d",
                self.digest_articles_summarised,
                self.digest_videos_summarised,
                self.digest_total_ranked,
            )
        if self.digest_errors:
            for err in self.digest_errors:
                logger.warning("  Digest error: %s", err)
        logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Validation helper
# ─────────────────────────────────────────────────────────────────────────────

def _validate_scraped_article(item) -> List[str]:
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
# Phase 1 runners — scraping
# ─────────────────────────────────────────────────────────────────────────────

def run_youtube_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    from app.scrapers.youtube_scraper import YouTubeScraper
    from app.database import get_db_session, YoutubeRepository

    logger.info("[YouTube] Starting scrape  (hours_lookback=%d)", hours)
    try:
        scraper = YouTubeScraper()
        items   = scraper.scrape(hours_lookback=hours)
    except Exception as exc:
        logger.error("[YouTube] Scraper crashed: %s", exc, exc_info=True)
        result.youtube_errors += 1
        return

    result.youtube_scraped = len(items)
    logger.info("[YouTube] Scraped %d items", len(items))

    valid_items = []
    for item in items:
        errors = _validate_scraped_article(item)
        if errors:
            logger.warning("[YouTube] Skipping invalid item %r: %s", item.title, errors)
            result.youtube_errors += 1
        else:
            valid_items.append(item)

    if dry_run:
        logger.info("[YouTube] DRY RUN — would insert %d items", len(valid_items))
        return

    if not valid_items:
        logger.info("[YouTube] Nothing valid to insert")
        return

    try:
        with get_db_session() as db:
            repo = YoutubeRepository(db)
            inserted, skipped = repo.bulk_create(valid_items)
            result.youtube_inserted = inserted
            result.youtube_skipped  = skipped
    except Exception as exc:
        logger.error("[YouTube] DB insertion failed: %s", exc, exc_info=True)
        result.youtube_errors += 1


def run_blogs_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    from app.scrapers.blog_scraper import BlogScraper
    from app.database import get_db_session, ArticleRepository

    logger.info("[Blogs] Starting scrape  (hours_lookback=%d)", hours)
    try:
        scraper = BlogScraper()
        items   = scraper.scrape(hours_lookback=hours)
    except Exception as exc:
        logger.error("[Blogs] Scraper crashed: %s", exc, exc_info=True)
        result.articles_errors += 1
        return

    result.articles_scraped = len(items)
    logger.info("[Blogs] Scraped %d items", len(items))

    valid_items = []
    for item in items:
        errors = _validate_scraped_article(item)
        if errors:
            logger.warning("[Blogs] Skipping invalid item %r: %s", item.title, errors)
            result.articles_errors += 1
        else:
            valid_items.append(item)

    if dry_run:
        logger.info("[Blogs] DRY RUN — would insert %d items", len(valid_items))
        return

    if not valid_items:
        logger.info("[Blogs] Nothing valid to insert")
        return

    try:
        with get_db_session() as db:
            repo = ArticleRepository(db)
            inserted, skipped = repo.bulk_create(valid_items)
            result.articles_inserted = inserted
            result.articles_skipped  = skipped
    except Exception as exc:
        logger.error("[Blogs] DB insertion failed: %s", exc, exc_info=True)
        result.articles_errors += 1


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2+3 runner — digest + email
# ─────────────────────────────────────────────────────────────────────────────

def run_digest_phase(
    hours: int,
    dry_run: bool,
    skip_email: bool,
    result: PipelineResult,
) -> None:
    from app.config import config
    from app.services.digest_service import DigestService
    from app.services.email_sender import EmailSender

    logger.info("[Digest] Starting digest + ranking phase")

    service = DigestService(
        config=config,
        hours_window=hours,
        top_n=10,
        dry_run=dry_run,
    )
    digest_result = service.run()

    result.digest_articles_summarised = digest_result.articles_summarised
    result.digest_videos_summarised   = digest_result.videos_summarised
    result.digest_total_ranked        = digest_result.total_ranked
    result.digest_errors              = digest_result.errors

    if digest_result.digest_response is None:
        logger.warning("[Digest] No digest generated (possibly no content in window).")
        return

    markdown = digest_result.digest_response.to_markdown()

    if skip_email:
        logger.info("[Digest] --skip-email set — printing digest to stdout:\n\n%s", markdown)
        return

    sender = EmailSender()
    if not sender.is_configured:
        logger.info(
            "[Digest] Email credentials not configured — printing digest to stdout.\n\n%s",
            markdown,
        )
        return

    recipient = os.getenv("RECIPIENT_EMAIL") or os.getenv("GMAIL_ADDRESS", "")
    sent = sender.send(
        to_address=recipient,
        subject=(
            f"Your AI News Digest — "
            f"{digest_result.digest_response.articles[0].title[:50]}"
            if digest_result.digest_response.articles
            else "Your AI News Digest — Top Stories"
        ),
        body_markdown=markdown,
    )
    if sent:
        logger.info("[Digest] Email delivered to %s", recipient)
    else:
        logger.warning("[Digest] Email delivery failed — check logs above.")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI News Aggregator Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run (scrape + digest + email)
  python run_pipeline.py

  # Skip scraping — use content already in the DB (fast, for dev/testing)
  python run_pipeline.py --skip-scraping

  # Skip scraping AND email — just regenerate summaries and print the digest
  python run_pipeline.py --skip-scraping --skip-email

  # Only scrape, do not run digest phase
  python run_pipeline.py --skip-digest

  # Scrape only YouTube, skip digest
  python run_pipeline.py --source youtube --skip-digest

  # Scrape but do not write to DB (dry run)
  python run_pipeline.py --dry-run

  # Custom lookback window
  python run_pipeline.py --hours 48
        """,
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=int(os.getenv("HOURS_LOOKBACK", "144")),
        help="How many hours back to look for content (default: 144 = 6 days)",
    )
    parser.add_argument(
        "--source",
        choices=["all", "youtube", "blogs"],
        default="all",
        help="Which scraper(s) to run (default: all)",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Skip Phase 1 entirely — use content already stored in the DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape but do NOT write to the database",
    )
    parser.add_argument(
        "--skip-digest",
        action="store_true",
        help="Skip Phase 2+3 (digest generation + email)",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Run digest generation but print the result instead of sending email",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AI NEWS AGGREGATOR — PIPELINE START")
    logger.info(
        "  hours=%d  source=%s  skip_scraping=%s  dry_run=%s  "
        "skip_digest=%s  skip_email=%s",
        args.hours, args.source, args.skip_scraping,
        args.dry_run, args.skip_digest, args.skip_email,
    )
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

    # ── Step 2: scraping (Phase 1) ────────────────────────────────────────
    if args.skip_scraping:
        logger.info("[Scraping] Skipped (--skip-scraping) — using existing DB content")
    else:
        if args.source in ("all", "youtube"):
            run_youtube_phase(args.hours, args.dry_run, result)

        if args.source in ("all", "blogs"):
            run_blogs_phase(args.hours, args.dry_run, result)

    # ── Step 3: digest + email (Phase 2+3) ───────────────────────────────
    if args.skip_digest:
        logger.info("[Digest] Skipped (--skip-digest)")
    elif args.dry_run:
        logger.info("[Digest] Skipped (--dry-run implies no digest phase)")
    else:
        run_digest_phase(args.hours, args.dry_run, args.skip_email, result)

    # ── Step 4: print summary ─────────────────────────────────────────────
    result.print_summary()

    total_errors = (
        result.youtube_errors
        + result.articles_errors
        + len(result.digest_errors)
    )
    if total_errors > 0:
        logger.warning("Pipeline completed with %d error(s)", total_errors)
        sys.exit(1)

    logger.info("Pipeline completed successfully.")


if __name__ == "__main__":
    main()