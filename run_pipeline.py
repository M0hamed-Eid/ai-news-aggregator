# run_pipeline.py
#
# Main entry point for the full data pipeline.
#
# Phase 1 — scrape YouTube + blogs + Source-Registry-driven sources → insert into PostgreSQL
# Phase 2 — generate AI summaries (DigestAgent) for unsummarised records
# Phase 3 — rank content (CuratorAgent) + build + send email (EmailAgent)
#
# Usage:
#   python run_pipeline.py
#   python run_pipeline.py --hours 48              # override lookback window
#   python run_pipeline.py --source blogs          # only blog scraper (hardcoded/legacy, not in the registry)
#   python run_pipeline.py --source youtube        # only YouTube scraper
#   python run_pipeline.py --source arxiv          # only arXiv scraper
#   python run_pipeline.py --source reddit         # only Reddit (r/MachineLearning etc.)
#   python run_pipeline.py --source government_uk  # only UK government RSS
#   python run_pipeline.py --source <key>          # --source now accepts ANY active key from the
#                                                   # Source Registry `sources` table (see
#                                                   # app/database/models/source.py) — it is no longer
#                                                   # a fixed argparse choices list. Run with an invalid
#                                                   # value to see the current valid keys printed back.
#                                                   # "blogs" and "youtube" remain special-cased CLI
#                                                   # values (see run_blogs_phase/run_youtube_phase below).
#   python run_pipeline.py --skip-scraping         # skip Phase 1, use existing DB content
#   python run_pipeline.py --skip-digest           # skip Phase 2+3
#   python run_pipeline.py --skip-email            # run digest but print instead of sending
#   python run_pipeline.py --dry-run               # scrape but do NOT write to DB
#
# Changes from previous version
# ----------------------------------
# 1. Added --skip-scraping CLI flag so Phase 1 can be bypassed when all
#    content is already in the DB (saves significant time during dev/testing).
# 2. Switched AI provider from OpenAI to Groq throughout.
#    OPENAI_API_KEY is no longer required; GROQ_API_KEY is used instead.
# 3. Extracted _run_article_phase() — the scrape/validate/bulk_create logic
#    shared by every Article-based phase (and, via repo_cls, YouTube too).
# 4. Per-source config (which subreddits, which arXiv categories, etc.) now
#    lives in the DB-driven Source Registry (`sources` table — see
#    app/database/models/source.py, backfilled by app/database/seed_sources.py)
#    instead of the old hardcoded ScraperConfig fields. SOURCE_PHASES and the
#    individual run_<name>_phase() functions for arxiv/github/reddit/funding/
#    government/huggingface are GONE, replaced by HANDLER_BUILDERS +
#    run_scraping_phases() below, which queries SourceRepository and
#    builds/dispatches a scraper instance from each row's .config. Adding a
#    future non-RSS API source is now a DB row + one HANDLER_BUILDERS entry;
#    adding a pure-RSS source is a DB row only — neither needs new code here.
#    run_blogs_phase (BlogScraper, hardcoded/legacy, deliberately NOT in the
#    registry) and run_youtube_phase (still its own repository/table) remain
#    their own functions and special-cased CLI values ("blogs", "youtube").
# 5. BEHAVIOR CHANGE: because --source's valid values now come from the DB
#    (the `sources` table) rather than a hardcoded argparse `choices=[...]`
#    list, validating an unrecognized --source value requires ONE database
#    query — even when --dry-run is set (previously --dry-run never touched
#    the DB at all). This is deliberate and disclosed here, not an accidental
#    regression: source config itself now lives in the DB, so there is no
#    longer a DB-free way to know the valid keys.

import argparse
import logging
import sys
import os
from dataclasses import dataclass, field
from typing import List, Tuple

from dotenv import load_dotenv

# ── Load .env BEFORE any project imports that read env vars ──────────────────
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Scraper classes needed to build HANDLER_BUILDERS below. These are now
# imported eagerly (rather than lazily inside each phase function, as before
# per-source config was DB-driven) because HANDLER_BUILDERS is a module-level
# dict of factories any registry row can invoke by its `handler` string at
# dispatch time. ───────────────────────────────────────────────────────────
from app.scrapers.arxiv_scraper import ArxivScraper
from app.scrapers.github_release_scraper import GitHubReleaseScraper
from app.scrapers.youtube_scraper import YouTubeScraper
from app.scrapers.federal_register_scraper import FederalRegisterScraper
from app.scrapers.huggingface_scraper import HuggingFaceScraper
from app.scrapers.rss_feed_scraper import RssFeedScraper


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

def _run_article_phase(
    label: str,
    scraper,
    hours: int,
    dry_run: bool,
    result: PipelineResult,
    repo_cls=None,
) -> bool:
    """
    Shared scrape -> validate -> bulk_create runner for every Article-based
    source, AND (via repo_cls=YoutubeRepository) for YouTube, which owns its
    own table/repository but otherwise follows the identical shape. `scraper`
    just needs a `.scrape(hours_lookback=...) -> List[ScrapedArticle]` method
    — this is what every BaseScraper subclass provides.

    repo_cls defaults to ArticleRepository. Passing YoutubeRepository lets
    run_youtube_phase() reuse this same flow instead of its old bespoke body
    (eliminating duplicate scrape/validate/insert logic between YouTube and
    the Article-based phases). Which PipelineResult counters get incremented
    (youtube_* vs articles_*) is chosen based on repo_cls, so the field names
    and log format ("[YouTube] Scraped %d items", etc.) are unchanged.

    Returns True unless the scraper crashed or the DB insertion failed — used
    by the Source Registry dispatch (run_scraping_phases) to call
    SourceRepository.mark_run() with an accurate success flag. Per-item
    validation failures are NOT treated as a phase failure — they're
    expected, routine noise-filtering, not a sign the source itself is broken.
    """
    from app.database import get_db_session, ArticleRepository, YoutubeRepository

    if repo_cls is None:
        repo_cls = ArticleRepository
    is_youtube = repo_cls is YoutubeRepository

    logger.info("[%s] Starting scrape  (hours_lookback=%d)", label, hours)
    try:
        items = scraper.scrape(hours_lookback=hours)
    except Exception as exc:
        logger.error("[%s] Scraper crashed: %s", label, exc, exc_info=True)
        if is_youtube:
            result.youtube_errors += 1
        else:
            result.articles_errors += 1
        return False

    if is_youtube:
        result.youtube_scraped += len(items)
    else:
        result.articles_scraped += len(items)
    logger.info("[%s] Scraped %d items", label, len(items))

    valid_items = []
    for item in items:
        errors = _validate_scraped_article(item)
        if errors:
            logger.warning("[%s] Skipping invalid item %r: %s", label, item.title, errors)
            if is_youtube:
                result.youtube_errors += 1
            else:
                result.articles_errors += 1
        else:
            valid_items.append(item)

    if dry_run:
        logger.info("[%s] DRY RUN — would insert %d items", label, len(valid_items))
        return True

    if not valid_items:
        logger.info("[%s] Nothing valid to insert", label)
        return True

    try:
        with get_db_session() as db:
            repo = repo_cls(db)
            inserted, skipped = repo.bulk_create(valid_items)
            if is_youtube:
                result.youtube_inserted += inserted
                result.youtube_skipped  += skipped
            else:
                result.articles_inserted += inserted
                result.articles_skipped  += skipped
    except Exception as exc:
        logger.error("[%s] DB insertion failed: %s", label, exc, exc_info=True)
        if is_youtube:
            result.youtube_errors += 1
        else:
            result.articles_errors += 1
        return False

    return True


def run_blogs_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    """BlogScraper stays hardcoded/legacy — deliberately NOT part of the Source Registry this milestone."""
    from app.scrapers.blog_scraper import BlogScraper
    _run_article_phase("Blogs", BlogScraper(), hours, dry_run, result)


def run_youtube_phase(hours: int, dry_run: bool, result: PipelineResult) -> None:
    """
    YouTube's config (channels, max_transcript_chars) now comes from its own
    Source Registry row (key="youtube") instead of ScraperConfig, but it
    still writes to its own table via YoutubeRepository — so it keeps its own
    runner function (special-cased in run_scraping_phases(), like "blogs")
    instead of going through the generic non-RSS registry loop there.
    """
    from app.database import get_db_session
    from app.database.repositories.source_repository import SourceRepository
    from app.database.repositories.youtube_repository import YoutubeRepository

    with get_db_session() as db:
        source = SourceRepository(db).get_by_key("youtube")

    if source is None or not source.is_active:
        logger.error(
            "[YouTube] No active 'youtube' row in the Source Registry — "
            "run `python -m app.database.seed_sources` to backfill it."
        )
        result.youtube_errors += 1
        return

    scraper = HANDLER_BUILDERS["youtube"](source.config)
    success = _run_article_phase(
        "YouTube", scraper, hours, dry_run, result, repo_cls=YoutubeRepository,
    )

    if not dry_run:
        with get_db_session() as db:
            SourceRepository(db).mark_run(source.id, success=success)


# ─────────────────────────────────────────────────────────────────────────────
# Source Registry dispatch — replaces the old SOURCE_PHASES list + the
# individual run_<name>_phase() functions for arxiv/github/reddit/funding/
# government/huggingface. Adding a future non-RSS API source is now a DB row
# (see app/database/seed_sources.py) + one HANDLER_BUILDERS entry below, not a
# new run_<name>_phase() function. Adding a future pure-RSS source is a DB
# row only — no code change at all.
# ─────────────────────────────────────────────────────────────────────────────

HANDLER_BUILDERS = {
    "arxiv": lambda cfg: ArxivScraper(categories=cfg["categories"]),
    "github_release": lambda cfg: GitHubReleaseScraper(repos=cfg["repos"]),
    "youtube": lambda cfg: YouTubeScraper(
        channels=cfg["channels"], max_transcript_chars=cfg.get("max_transcript_chars", 8000)
    ),
    "federal_register": lambda cfg: FederalRegisterScraper(terms=cfg["terms"]),
    "huggingface": lambda cfg: HuggingFaceScraper(fetch_limit=cfg.get("fetch_limit", 100)),
}


def _validate_source_handlers(sources) -> None:
    """
    Fail fast and loud (a RuntimeError, not a silent log) if any active,
    non-RSS Source row references a handler HANDLER_BUILDERS doesn't
    recognize — a misconfigured registry row should crash the run naming
    exactly which source key is broken, not silently scrape nothing for it.
    """
    for source in sources:
        if source.adapter_type != "rss" and source.handler not in HANDLER_BUILDERS:
            raise RuntimeError(
                f"Source registry misconfiguration: source key={source.key!r} "
                f"(adapter_type={source.adapter_type!r}) has handler={source.handler!r}, "
                f"which is not a recognized handler. Known handlers: {sorted(HANDLER_BUILDERS)}"
            )


def run_scraping_phases(
    source_filter: str, hours: int, dry_run: bool, result: PipelineResult
) -> None:
    """
    Dispatch every scraping phase for this run.

    "blogs" and "youtube" are special-cased CLI values, resolved by their own
    runner functions above (blogs isn't in the registry at all; youtube is,
    but keeps its own repository/table). Every other active Source Registry
    row is grouped by adapter_type:
      - adapter_type="rss" rows are FLATTENED together into ONE RssFeedScraper
        call (their `feeds` lists combined into one list) — this preserves
        Reddit's per-feed delay_after_seconds pacing, which depends on
        sequential iteration WITHIN a single RssFeedScraper.scrape() call.
        Instantiating one RssFeedScraper per row would break that rate-limit
        pacing (each instance would race the others instead of pacing itself).
      - every other row gets its own scraper instance via
        HANDLER_BUILDERS[row.handler](row.config) and its own
        _run_article_phase(row.name, scraper, hours, dry_run, result) call.

    After a non-dry-run attempt, SourceRepository.mark_run() is called for
    every row that was attempted this run (both RSS-grouped rows and
    individual API rows).
    """
    from app.database import get_db_session
    from app.database.repositories.source_repository import SourceRepository

    if source_filter in ("all", "blogs"):
        run_blogs_phase(hours, dry_run, result)
    if source_filter in ("all", "youtube"):
        run_youtube_phase(hours, dry_run, result)
    if source_filter in ("blogs", "youtube"):
        return

    with get_db_session() as db:
        source_repo = SourceRepository(db)

        # Validate every active row (not just the ones about to run this
        # invocation) so a misconfigured registry row is caught even on a
        # narrow --source run, not only when that particular row is picked.
        active = source_repo.get_active()
        _validate_source_handlers(active)

        if source_filter == "all":
            # youtube is excluded here — already handled by run_youtube_phase() above.
            sources = [s for s in active if s.key != "youtube"]
        else:
            sources = source_repo.get_active_by_keys([source_filter])

        # Pull out plain data before the session closes — each phase call
        # below opens its OWN get_db_session() for the actual insert, and ORM
        # objects shouldn't be used past their session's lifetime.
        rss_rows = [(s.id, s.config.get("feeds", [])) for s in sources if s.adapter_type == "rss"]
        handler_rows = [
            (s.id, s.name, s.handler, s.config) for s in sources if s.adapter_type != "rss"
        ]

    attempts: List[Tuple[int, bool]] = []

    if rss_rows:
        combined_feeds: List[dict] = []
        for _, feeds in rss_rows:
            combined_feeds.extend(feeds)
        scraper = RssFeedScraper(source_name="rss_sources", feeds=combined_feeds)
        success = _run_article_phase("RSS Sources", scraper, hours, dry_run, result)
        attempts.extend((source_id, success) for source_id, _ in rss_rows)

    for source_id, name, handler, cfg in handler_rows:
        scraper = HANDLER_BUILDERS[handler](cfg)
        success = _run_article_phase(name, scraper, hours, dry_run, result)
        attempts.append((source_id, success))

    if not dry_run and attempts:
        with get_db_session() as db:
            source_repo = SourceRepository(db)
            for source_id, success in attempts:
                source_repo.mark_run(source_id, success=success)


def run_embedding_phase(result: PipelineResult) -> None:
    """
    Embeds every article/video that doesn't have an embedding yet.
    Uses summary if it exists (cleaner, shorter), falls back to the raw
    content/title otherwise — so this can run right after scraping, without
    waiting for the summarization phase to finish first.
    """
    from app.database import get_db_session
    from app.database.repositories.embedding_repository import EmbeddingRepository
    from app.database.repositories.article_repository import ArticleRepository
    from app.database.repositories.youtube_repository import YoutubeRepository
    from app.embeddings.embedding_service import embed_text

    logger.info("[Embeddings] Starting embedding phase")
    embedded, errors = 0, 0

    with get_db_session() as db:
        emb_repo = EmbeddingRepository(db)

        for article in ArticleRepository(db).get_all(limit=1000):
            if emb_repo.exists_for("article", article.id):
                continue
            text = article.summary or (article.content or "")[:2000] or article.title
            try:
                emb_repo.upsert("article", article.id, embed_text(text))
                embedded += 1
            except Exception:
                logger.exception(f"[Embeddings] Failed on article id={article.id}")
                errors += 1

        for video in YoutubeRepository(db).get_all(limit=1000):
            if emb_repo.exists_for("youtube_video", video.id):
                continue
            text = video.summary or (video.content or "")[:2000] or video.title
            try:
                emb_repo.upsert("youtube_video", video.id, embed_text(text))
                embedded += 1
            except Exception:
                logger.exception(f"[Embeddings] Failed on video id={video.id}")
                errors += 1

    logger.info(f"[Embeddings] Done. embedded={embedded} errors={errors}")

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2+3 runner — digest + email
# ─────────────────────────────────────────────────────────────────────────────

def run_digest_phase(
    hours: int,
    dry_run: bool,
    skip_email: bool,
    result: PipelineResult,
) -> None:
    """
    Multi-user (2026-07-12): DigestService now ranks + builds one digest per
    active recipient (see app/services/digest_service.py, app/services/
    recipients.py) instead of a single global digest_response. This function
    loops digest_result.digest_responses and sends one email per recipient,
    to that recipient's own address — not a single hardcoded RECIPIENT_EMAIL.
    The debug_last_email.html dump (for an already-fixed bug, per this file's
    own changelog) is removed rather than namespaced per recipient — it was
    dead debug scaffolding, not something worth keeping in a per-user loop.
    """
    from app.config import config
    from app.services.digest_service import DigestService
    from app.services.email_sender import EmailSender
    from app.services.email_template import render_email_html

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

    if not digest_result.digest_responses:
        logger.warning("[Digest] No digest generated for any recipient (possibly no content in window).")
        return

    sender = EmailSender()
    sender_configured = sender.is_configured

    for recipient_digest in digest_result.digest_responses:
        recipient = recipient_digest.recipient
        response = recipient_digest.response
        to_address = recipient.profile.email

        html_body = render_email_html(response)
        text_body = response.to_markdown()

        if skip_email:
            logger.info(
                "[Digest] --skip-email set — printing digest for %s to stdout:\n\n%s",
                to_address, html_body,
            )
            continue

        if not sender_configured:
            logger.info(
                "[Digest] Email credentials not configured — printing digest for %s to stdout.\n\n%s",
                to_address, html_body,
            )
            continue

        if not to_address:
            logger.warning("[Digest] Recipient has no email address — skipping send.")
            continue

        sent = sender.send(
            to_address=to_address,
            subject=(
                f"Your AI News Digest — {response.articles[0].title[:50]}"
                if response.articles
                else "Your AI News Digest — Top Stories"
            ),
            body_html=html_body,
            body_text=text_body,
        )
        if sent:
            logger.info("[Digest] Email delivered to %s", to_address)
            # Log the send on OUR side (pipeline-owned digest_log table) so
            # the profile page can show "digests received: N" without the
            # pipeline ever writing into a Django-owned table.
            if recipient.user_id is not None:
                try:
                    from app.database import get_db_session
                    from app.database.repositories.digest_log_repository import DigestLogRepository
                    with get_db_session() as db:
                        DigestLogRepository(db).log_sent(recipient.user_id)
                except Exception as exc:
                    logger.error("[Digest] Failed to log digest send for user_id=%s — %s", recipient.user_id, exc)
        else:
            logger.warning("[Digest] Email delivery failed for %s — check logs above.", to_address)


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

  # Scrape only one Source Registry key (any active key, e.g. reddit/arxiv/government_uk)
  python run_pipeline.py --source reddit --skip-digest

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
        type=str,
        default="all",
        help=(
            "Which scraper(s) to run (default: all). Accepts 'all', 'blogs', "
            "'youtube', or any active key from the Source Registry `sources` "
            "table (e.g. 'arxiv', 'github_release', 'reddit', 'government_us', "
            "'government_uk', 'government_nist', 'funding_crunchbase', "
            "'huggingface_model') — this is no longer a fixed choices list; "
            "run with an invalid value to see the current valid keys."
        ),
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

    # ── --source validation ────────────────────────────────────────────────
    # --source's valid values now come from the DB (Source Registry `sources`
    # table) rather than a hardcoded argparse `choices=[...]` list, so
    # validating an unrecognized value requires ONE query here — even in
    # --dry-run mode, which previously never touched the DB at all. Deliberate,
    # disclosed behavior change (see the module docstring at the top of this file).
    if args.source not in ("all", "blogs"):
        from app.database import get_db_session
        from app.database.repositories.source_repository import SourceRepository

        with get_db_session() as db:
            valid_keys = sorted(s.key for s in SourceRepository(db).get_active())

        if args.source not in valid_keys:
            print(
                f"Error: unknown --source {args.source!r}.\n"
                f"Valid values: 'all', 'blogs', "
                f"{', '.join(repr(k) for k in valid_keys)}",
                file=sys.stderr,
            )
            sys.exit(1)

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
        run_scraping_phases(args.source, args.hours, args.dry_run, result)

    # ── Step 3: embedding (Phase 1.5) ─────────────────────────────────────
    if not args.dry_run:
        logger.info("[Embedding] Starting embedding phase")
        run_embedding_phase(result)
    else:
        logger.info("[Embedding] Skipped (dry-run mode)")

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
