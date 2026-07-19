# run_pipeline.py
#
# Main entry point for the full data pipeline.
#
# Phase 1 — scrape YouTube + blogs + Source-Registry-driven sources → insert into PostgreSQL.
#           M10: visibility='user' (user-submitted) sources have their schedule_hours
#           floor ACTUALLY enforced here (_due_for_scraping()) — skipped if not yet
#           due. The 9 curated (visibility='global') sources' every-run behavior is
#           unchanged; schedule_hours remains metadata-only for them.
# Phase 2 — enrich content (EnrichmentAgent: summary + M8 structured fields) for unenriched records
# Phase 3 — build + send email from each recipient's CURRENT ranking (EmailAgent) — ranking
#           itself is computed separately, on its own schedule (app/tasks/ranking_tasks.py,
#           M9's deterministic RankingService — CuratorAgent/LLM ranking is gone)
# Phase 3.5 — cross-source clustering + heuristic quality scoring (M8)
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

    clustering_clusters: int = 0
    clustering_items:    int = 0

    scoring_scored: int = 0
    scoring_errors: int = 0

    trend_dimensions_computed: int = 0
    trend_topics_trending: int = 0
    trend_entities_trending: int = 0

    stt_dispatched: int = 0

    deep_video_processed: int = 0
    deep_video_errors: int = 0

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
        if self.clustering_clusters or self.clustering_items:
            logger.info(
                "  Clusters : %4d cluster(s)  %4d item(s) clustered",
                self.clustering_clusters, self.clustering_items,
            )
        if self.scoring_scored or self.scoring_errors:
            logger.info(
                "  Scoring  : scored=%4d  errors=%4d",
                self.scoring_scored, self.scoring_errors,
            )
        if self.trend_dimensions_computed:
            logger.info(
                "  Trends   : %4d dimension(s) computed  %4d topic(s) trending  %4d entit(y/ies) trending",
                self.trend_dimensions_computed, self.trend_topics_trending, self.trend_entities_trending,
            )
        if self.stt_dispatched:
            logger.info("  STT      : %4d job(s) dispatched to the stt queue", self.stt_dispatched)
        if self.deep_video_processed or self.deep_video_errors:
            logger.info(
                "  DeepVideo: processed=%4d  errors=%4d",
                self.deep_video_processed, self.deep_video_errors,
            )
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
    # M12: a YouTube item (video_id set) with no content is a caption-less
    # video queued for STT (app/tasks/stt_tasks.py) — not invalid. Every
    # other source (blogs, arxiv, etc.) still requires real content.
    is_youtube_stub = getattr(item, "video_id", None) and not item.content
    if not is_youtube_stub and (not item.content or len(item.content.strip()) < 50):
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
        # M7: no default cap — omit max_transcript_chars from a source row's
        # config to capture full transcripts (see seed_sources.py).
        channels=cfg["channels"], max_transcript_chars=cfg.get("max_transcript_chars")
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


def _due_for_scraping(source) -> bool:
    """
    Fetch-frequency floor enforcement (M10) — scoped to visibility='user'
    sources ONLY. The 9 admin-seeded (visibility='global') sources keep
    their existing behavior of scraping on EVERY pipeline run regardless of
    schedule_hours, exactly as before M10 — schedule_hours has always been
    "metadata only, not a real background scheduler" for them (see
    app/database/models/source.py), and there is no reason to change
    already-working, already-tested behavior for the curated registry.

    User-submitted sources are different: schedule_hours is the abuse-
    control floor set at submission time (app/tasks/source_submission_tasks.py,
    MIN_USER_SOURCE_SCHEDULE_HOURS), and it needs to actually mean
    something, or "fetch-frequency floors" (an explicit M10 Core
    requirement) would be pure fiction. A user source with no last_run_at
    yet (never scraped) is always due.
    """
    if getattr(source, "visibility", "global") != "user":
        return True
    if source.last_run_at is None:
        return True
    if not source.schedule_hours:
        return True
    from datetime import datetime, timedelta, timezone as dt_timezone
    return datetime.now(dt_timezone.utc) - source.last_run_at >= timedelta(hours=source.schedule_hours)


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

        # M10 fetch-frequency floor — visibility='user' sources only, see
        # _due_for_scraping()'s own docstring for why global sources are untouched.
        skipped_not_due = [s.key for s in sources if not _due_for_scraping(s)]
        sources = [s for s in sources if _due_for_scraping(s)]
        if skipped_not_due:
            logger.info(
                "run_scraping_phases: skipping %d user source(s) not yet due for their schedule_hours floor: %s",
                len(skipped_not_due), skipped_not_due,
            )

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

    from app.database.repositories.youtube_repository import YoutubeRepository

    for source_id, name, handler, cfg in handler_rows:
        scraper = HANDLER_BUILDERS[handler](cfg)
        # BUGFIX: a user-submitted source with handler="youtube" (custom
        # YouTube channel sources) is NOT excluded from this generic loop —
        # only the curated row is excluded, by key, in the `sources` filter
        # above. Without repo_cls=YoutubeRepository here, its ScrapedArticle
        # objects (which carry video_id/channel_id/transcript_segments)
        # would insert into `articles` via ArticleRepository's default
        # (wrong dedup key: url instead of video_id; also silently skips
        # the STT-queue side effect for caption-less videos). See
        # .wolf/buglog.json for the full writeup.
        repo_cls = YoutubeRepository if handler == "youtube" else None
        success = _run_article_phase(name, scraper, hours, dry_run, result, repo_cls=repo_cls)
        attempts.append((source_id, success))

    if not dry_run and attempts:
        with get_db_session() as db:
            source_repo = SourceRepository(db)
            for source_id, success in attempts:
                source_repo.mark_run(source_id, success=success)


def run_stt_dispatch_phase(result: PipelineResult) -> None:
    """
    M12 — claims queued stt_jobs rows (queued -> running) and dispatches
    transcribe_video_task on the dedicated "stt" queue (app/celery_app.py).
    Runs in its OWN get_db_session() AFTER run_scraping_phases' transactions
    have already committed, so a job is only ever claimed once its
    youtube_videos/stt_jobs rows are safely visible on every connection —
    this is what avoids racing YoutubeRepository.bulk_create's
    commit-on-exit (dispatching from inside that transaction would risk the
    stt worker looking up a row before it's committed).

    Cheap and synchronous — this only enqueues Celery messages, it does NOT
    wait for transcription (that happens asynchronously on the stt worker,
    which per docs/ROADMAP.md should run from a residential-IP host). A
    caption-less video's content lands on a LATER pipeline pass once its
    async STT task completes — get_unenriched() then picks it up
    automatically, with zero special-casing (M12 success criterion 2).
    """
    from app.database import get_db_session
    from app.database.repositories.stt_job_repository import SttJobRepository
    from app.tasks.stt_tasks import transcribe_video_task

    logger.info("[STT] Starting dispatch phase")

    with get_db_session() as db:
        stt_repo = SttJobRepository(db)
        queued_jobs = stt_repo.get_queued(limit=20)
        claimed = [(job.content_type, job.content_id) for job in queued_jobs]
        for content_type, content_id in claimed:
            stt_repo.upsert_status(content_type=content_type, content_id=content_id, status="running")

    for _content_type, content_id in claimed:
        transcribe_video_task.delay(content_id=content_id)
        result.stt_dispatched += 1

    logger.info("[STT] Dispatched %d job(s) to the stt queue", len(claimed))


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


def run_clustering_phase(result: PipelineResult) -> None:
    """
    Rebuilds content_clusters/content_cluster_members WHOLESALE (M8):
    Union-Find over a pgvector k-NN graph. For every embedded item, pull its
    nearest neighbors via EmbeddingRepository.find_similar() (cross-source —
    content_type=None — since dedup/Related must span sources), keep edges
    above SIMILARITY_THRESHOLD, then union connected items into the same
    component. This is single-linkage agglomerative clustering restricted
    to a k-NN graph — the standard, efficient way to do "agglomerative over
    pgvector neighbors" (the roadmap's own wording) without an O(n^2) full
    pairwise distance matrix, and needs no new dependency (stdlib Union-Find,
    order-independent, ~20 lines).

    Wholesale replace every run — clustering is a global, non-user
    computation (Principle 1: ingest once, never per-user), and at this
    corpus's current scale (~6-8k items) a full rebuild is seconds-to-low-
    minutes of work — same "replace, don't accumulate" convention as
    UserRanking/UserAffinity. Revisit only if corpus size grows an order of
    magnitude.
    """
    from app.database import get_db_session
    from app.database.models.article import Article
    from app.database.models.embedding import Embedding
    from app.database.repositories.embedding_repository import EmbeddingRepository
    from app.database.repositories.content_cluster_repository import ContentClusterRepository

    # 0.85 was tried first and produced a real single-linkage chaining
    # failure live: a 60-item "mega-cluster" of unrelated Hugging Face model
    # uploads, bridged transitively through a few genuinely-high-similarity
    # pairs (~0.95) even though most pairs in the cluster were only ~0.55-0.69
    # similar. 0.92 still left a smaller but real mega-cluster of the SAME
    # source. Root cause (confirmed live, not guessed): huggingface_model
    # articles/summaries are heavily templated ("A new model has been
    # published on the Hugging Face Hub, offering...") — the boilerplate
    # phrasing dominates the embedding, so unrelated model uploads collide
    # in embedding space regardless of actual content difference. Same class
    # of known low-signal noise as this source's ingest-time issue (see
    # .wolf/cerebrum.md: "HF's createdAt sort being mostly noise"). Excluded
    # from cross-source STORY clustering entirely — clustering exists to
    # dedup the same real-world story covered by multiple outlets, not to
    # group generically-similar catalog entries from one firehose source.
    EXCLUDED_ARTICLE_SOURCES = {"huggingface_model"}

    SIMILARITY_THRESHOLD = 0.92
    NEIGHBORS_PER_ITEM = 8
    MAX_ITEMS = 20_000  # generous headroom above current corpus size (~6-8k)

    logger.info("[Clustering] Starting clustering phase")

    with get_db_session() as db:
        emb_repo = EmbeddingRepository(db)

        excluded_article_ids = {
            aid for (aid,) in db.query(Article.id).filter(Article.source.in_(EXCLUDED_ARTICLE_SOURCES))
        }
        all_embeddings = [
            e for e in db.query(Embedding).limit(MAX_ITEMS).all()
            if not (e.content_type == "article" and e.content_id in excluded_article_ids)
        ]
        items = [(e.content_type, e.content_id) for e in all_embeddings]
        index = {key: i for i, key in enumerate(items)}
        parent = list(range(len(items)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # path compression
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[ry] = rx

        for i, embedding_row in enumerate(all_embeddings):
            neighbors = emb_repo.find_similar(
                embedding_row.embedding, content_type=None, limit=NEIGHBORS_PER_ITEM + 1,
            )
            for neighbor_row, similarity in neighbors:
                key = (neighbor_row.content_type, neighbor_row.content_id)
                if key == items[i] or similarity < SIMILARITY_THRESHOLD:
                    continue
                j = index.get(key)
                if j is not None:
                    union(i, j)

        groups: dict = {}
        for i, key in enumerate(items):
            groups.setdefault(find(i), []).append(key)

        clusters = list(groups.values())
        total_members = ContentClusterRepository(db).replace_all(clusters)

    multi_item_clusters = sum(1 for c in clusters if len(c) >= 2)
    logger.info(
        "[Clustering] Done. %d item(s) embedded, %d cluster(s) with 2+ members, %d item(s) clustered",
        len(items), multi_item_clusters, total_members,
    )
    result.clustering_clusters = multi_item_clusters
    result.clustering_items = total_members


def run_scoring_phase(result: PipelineResult) -> None:
    """
    Quality score v1 (heuristic) + a snapshot of the exact feature vector
    that produced it (M8, Principle 7: "log features now so they become
    future ML training data"). Weights here are a documented, adjustable
    starting point, not a tuned model — the point of content_scores.features
    is capturing the INPUTS for future ML training, not the formula being
    "correct" yet. `popularity` is reserved (None) — the [Nice-to-have]
    popularity re-fetch job hasn't shipped this milestone.
    """
    import math
    from datetime import datetime, timezone

    from app.database import get_db_session
    from app.database.repositories.article_repository import ArticleRepository
    from app.database.repositories.youtube_repository import YoutubeRepository
    from app.database.repositories.content_enrichment_repository import ContentEnrichmentRepository
    from app.database.repositories.content_entity_repository import ContentEntityRepository
    from app.database.repositories.content_topic_repository import ContentTopicRepository
    from app.database.repositories.content_score_repository import ContentScoreRepository
    from app.database.models.content_enrichment import ContentEnrichment
    from app.database.models.content_entity import ContentEntity
    from app.database.models.content_topic import ContentTopic

    SCORE_VERSION = "v1"
    MAX_ITEMS = 20_000  # same generous headroom as run_clustering_phase

    logger.info("[Scoring] Starting quality-scoring phase")
    scored = errors = 0

    with get_db_session() as db:
        score_repo = ContentScoreRepository(db)

        for content_type, repo_cls in (("article", ArticleRepository), ("youtube_video", YoutubeRepository)):
            for item in repo_cls(db).get_all(limit=MAX_ITEMS):
                try:
                    enrichment = (
                        db.query(ContentEnrichment)
                        .filter_by(content_type=content_type, content_id=item.id)
                        .first()
                    )
                    content_length = len(item.content or "")
                    length_score = min(1.0, math.log1p(content_length) / math.log1p(5000))
                    entity_count = (
                        db.query(ContentEntity).filter_by(content_type=content_type, content_id=item.id).count()
                    )
                    topic_count = (
                        db.query(ContentTopic).filter_by(content_type=content_type, content_id=item.id).count()
                    )
                    age_days = (datetime.now(timezone.utc) - item.published_at).total_seconds() / 86400.0
                    freshness = math.exp(-max(age_days, 0.0) / 14.0)

                    features = {
                        "has_enrichment": enrichment is not None,
                        "content_length_score": round(length_score, 4),
                        "entity_count": entity_count,
                        "topic_count": topic_count,
                        "freshness": round(freshness, 4),
                        "technical_depth": enrichment.technical_depth if enrichment else None,
                        "popularity": None,
                    }
                    score = (
                        0.30 * (1.0 if enrichment is not None else 0.0)
                        + 0.20 * length_score
                        + 0.15 * min(1.0, entity_count / 5.0)
                        + 0.15 * min(1.0, topic_count / 3.0)
                        + 0.20 * freshness
                    )

                    score_repo.upsert(content_type, item.id, score, SCORE_VERSION, features)
                    scored += 1
                except Exception:
                    logger.exception(f"[Scoring] Failed on {content_type} id={item.id}")
                    errors += 1

    logger.info(f"[Scoring] Done. scored={scored} errors={errors}")
    result.scoring_scored = scored
    result.scoring_errors = errors


def run_trend_computation_phase(result: PipelineResult) -> None:
    """
    Burst detection (M11) — deliberately LLM-free, pure SQL/statistics. Runs
    as the 6th phase of the existing 6-hourly pipeline chain rather than a
    standalone daily schedule: nothing else in this codebase chains tasks by
    completion signal (only fixed clock offsets with a "generous buffer",
    e.g. the 3:00/3:15 nightly jobs assuming the midnight pipeline finished)
    — a new phase here avoids inventing that same guess, and recomputing
    "today"'s row up to 4x/day (once per 6-hourly run) keeps the Home
    Trending module from going stale for up to 19 hours the way a fixed
    once-daily job would.

    For every (dimension, key) pair — every active TaxonomyTopic slug, and
    every entity_id ever mentioned in content_entities — computes TODAY's
    UTC mention count, compares it to a 30-day trailing baseline read back
    from already-persisted `trends` rows (never recomputed), and flags
    is_trending via a z-score threshold. Two guards directly address the
    roadmap's own named risk ("false positives on low-volume topics"): a
    brand-new topic/entity has no baseline history and structurally cannot
    trend on day 1.
    """
    import statistics
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone

    from app.database import get_db_session
    from app.database.models.article import Article
    from app.database.models.content_entity import ContentEntity
    from app.database.models.content_topic import ContentTopic
    from app.database.models.taxonomy_topic import TaxonomyTopic
    from app.database.models.youtube_video import YoutubeVideo
    from app.database.repositories.taxonomy_topic_repository import TaxonomyTopicRepository
    from app.database.repositories.trend_repository import TrendRepository

    MIN_MENTIONS_TODAY = 3
    MIN_BASELINE_DAYS_WITH_DATA = 5   # of the trailing 30 days, how many must have >=1 mention
    MIN_STDDEV_FLOOR = 1.0            # prevents divide-by-near-zero for a perfectly flat metric
    Z_THRESHOLD = 2.0
    BASELINE_WINDOW_DAYS = 30

    logger.info("[Trends] Starting burst-detection phase")

    today = datetime.now(timezone.utc).date()
    baseline_start = today - timedelta(days=BASELINE_WINDOW_DAYS)
    baseline_end = today - timedelta(days=1)
    # Anything published before the baseline window is irrelevant to today's
    # count or the 30-day baseline — no need to load the whole corpus.
    window_start_dt = datetime.combine(baseline_start, datetime.min.time(), tzinfo=timezone.utc)

    dimensions_computed = topics_trending = entities_trending = 0

    with get_db_session() as db:
        trend_repo = TrendRepository(db)

        recent_article_dates = {
            aid: pub.date() for aid, pub in db.query(Article.id, Article.published_at)
            .filter(Article.published_at >= window_start_dt).all()
        }
        recent_video_dates = {
            vid: pub.date() for vid, pub in db.query(YoutubeVideo.id, YoutubeVideo.published_at)
            .filter(YoutubeVideo.published_at >= window_start_dt).all()
        }

        def _today_counts(rows) -> dict:
            """rows: iterable of (dimension_key, content_type, content_id) -> {key: today_mention_count}."""
            counts: dict = defaultdict(int)
            for dim_key, content_type, content_id in rows:
                pub_date = (
                    recent_article_dates.get(content_id) if content_type == "article"
                    else recent_video_dates.get(content_id)
                )
                if pub_date == today:
                    counts[dim_key] += 1
            return counts

        topic_today = _today_counts(
            # Joined to TaxonomyTopic so dim_key is the SLUG (a string) —
            # _compute_and_upsert looks topics up by slug (get_active_slugs()),
            # not by the raw integer taxonomy_topic_id ContentTopic itself stores.
            db.query(TaxonomyTopic.slug, ContentTopic.content_type, ContentTopic.content_id)
            .join(TaxonomyTopic, ContentTopic.taxonomy_topic_id == TaxonomyTopic.id)
            .all()
        )
        entity_today = _today_counts(
            db.query(ContentEntity.entity_id, ContentEntity.content_type, ContentEntity.content_id).all()
        )

        def _compute_and_upsert(dimension: str, key: str, today_count: int) -> bool:
            history = trend_repo.get_history(dimension, key, baseline_start, baseline_end)
            nonzero_days = sum(1 for h in history if h.mention_count > 0)

            if today_count < MIN_MENTIONS_TODAY or nonzero_days < MIN_BASELINE_DAYS_WITH_DATA:
                baseline_mean = statistics.fmean(h.mention_count for h in history) if history else 0.0
                baseline_stddev = statistics.pstdev(h.mention_count for h in history) if len(history) > 1 else 0.0
                z_score, is_trending = None, False
            else:
                counts = [h.mention_count for h in history]
                baseline_mean = statistics.fmean(counts)
                baseline_stddev = statistics.pstdev(counts)
                effective_stddev = max(baseline_stddev, MIN_STDDEV_FLOOR)
                z_score = (today_count - baseline_mean) / effective_stddev
                is_trending = z_score >= Z_THRESHOLD

            trend_repo.upsert_daily(
                dimension=dimension, key=key, date=today, mention_count=today_count,
                baseline_mean=baseline_mean, baseline_stddev=baseline_stddev,
                z_score=z_score, is_trending=is_trending,
            )
            return is_trending

        for slug in TaxonomyTopicRepository(db).get_active_slugs():
            if _compute_and_upsert("topic", slug, topic_today.get(slug, 0)):
                topics_trending += 1
            dimensions_computed += 1

        for entity_id in trend_repo.get_mentioned_entity_ids():
            if _compute_and_upsert("entity", str(entity_id), entity_today.get(entity_id, 0)):
                entities_trending += 1
            dimensions_computed += 1

    logger.info(
        "[Trends] Done. %d dimension(s) computed, %d topic(s) trending, %d entity(ies) trending",
        dimensions_computed, topics_trending, entities_trending,
    )
    result.trend_dimensions_computed = dimensions_computed
    result.trend_topics_trending = topics_trending
    result.trend_entities_trending = entities_trending


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
    from app.services.digest_service import DigestService, _DJANGO_BASE_URL
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

        # base_url reuses digest_service's EXISTING _DJANGO_BASE_URL (already
        # used for /r/<token>/ click-tracking links in this same response) —
        # no new env var, no duplicated os.getenv call. Lets the digest's
        # per-source fallback banner use real branded artwork instead of a
        # solid color when a source has no article.image_url of its own.
        html_body = render_email_html(response, base_url=_DJANGO_BASE_URL)
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
# Deep Media (M12) — chunking + map-reduce hierarchical summarization
# ─────────────────────────────────────────────────────────────────────────────

# 20 minutes — splits "tutorials often <15min" from "talks/podcasts often
# 20-90+min". Below this, today's single-pass enrichment is unchanged and
# available to everyone; at/above it, a video gets chaptered chunks (this
# phase) PLUS a richer reduce-step enrichment pass. Computed globally for
# every qualifying video regardless of any viewer's plan (Architecture
# Principle 1 — "ingest once, personalize later... never per-user"); only
# the SERVING layer gates the chaptered UI behind Pro (see
# web/apps/news/views.py::VideoDetailView, which duplicates this exact value
# with a cross-reference comment — the two-ORM split means it can't be
# imported directly from here).
LONG_VIDEO_THRESHOLD_SECONDS = 1200

# ~10 minutes per chunk, snapped to segment boundaries (never split
# mid-segment). A trailing sliver under this many seconds merges into the
# previous chunk instead of standing alone as a near-empty final "chapter".
CHUNK_TARGET_SECONDS = 600
CHUNK_TRAILING_MERGE_SECONDS = 90


def _build_transcript_chunks(segments: List[dict]) -> List[Tuple[float, float, List[dict]]]:
    """
    Groups transcript_segments into ~CHUNK_TARGET_SECONDS-long chunks.
    Returns [(start_seconds, end_seconds, segment_list), ...] in order.
    """
    if not segments:
        return []

    chunks: List[Tuple[float, float, List[dict]]] = []
    current: List[dict] = []
    chunk_start = segments[0]["start"]

    for seg in segments:
        if not current:
            chunk_start = seg["start"]
        current.append(seg)
        seg_end = seg["start"] + seg["duration"]
        if seg_end - chunk_start >= CHUNK_TARGET_SECONDS:
            chunks.append((chunk_start, seg_end, current))
            current = []

    if current:
        tail_start = current[0]["start"]
        tail_end = current[-1]["start"] + current[-1]["duration"]
        if chunks and (tail_end - tail_start) < CHUNK_TRAILING_MERGE_SECONDS:
            prev_start, _prev_end, prev_segments = chunks[-1]
            chunks[-1] = (prev_start, tail_end, prev_segments + current)
        else:
            chunks.append((tail_start, tail_end, current))

    return chunks


def run_deep_video_phase(result: PipelineResult) -> None:
    """
    M12 success criterion 1: a long video gets a chaptered summary with
    working timestamp deep-links. For every video at/above
    LONG_VIDEO_THRESHOLD_SECONDS with transcript_segments but no
    content_chunks yet:

      1. MAP — chunk transcript_segments (~10min each) and summarize each
         chunk via ChunkSummaryAgent into a {chapter_title, summary}.
      2. REDUCE — re-run the EXISTING EnrichmentAgent.generate(), fed the
         concatenated chunk summaries (prefixed with their [start-end]
         timestamps) instead of video.content. This incidentally fixes a
         real pre-existing gap: EnrichmentAgent truncates all content to
         content[:10_000] chars, so a 2-hour video's normal single-pass
         enrichment (run_digest_phase, above) only ever saw its first ~10k
         characters. Chunk summaries comfortably fit in one call regardless
         of video length, so long videos get a STRICTLY BETTER enrichment
         after this phase, not just chapters.

    Reuses DigestService._persist_enrichment/_reembed directly (same 3
    tables + re-embed every other enrichment call writes through) rather
    than duplicating that persistence logic — this phase's enrichment
    output is a second, later, better pass over the SAME row, not a
    different kind of write.

    Runs as an additional phase in the existing 6-hourly chain (matches
    M11's own "don't invent a new schedule" reasoning for run_trend_
    computation_phase) rather than a standalone job, right after
    run_digest_phase so it upgrades the normal single-pass enrichment
    run_digest_phase just wrote, and before clustering so clustering works
    off the upgraded embedding too.
    """
    from app.agents.chunk_summary_agent import CHUNK_SUMMARY_VERSION, ChunkSummaryAgent
    from app.agents.enrichment_agent import EnrichmentAgent
    from app.config import config
    from app.database import get_db_session
    from app.database.models.youtube_video import YoutubeVideo
    from app.database.repositories.content_chunk_repository import ContentChunkRepository
    from app.database.repositories.taxonomy_topic_repository import TaxonomyTopicRepository
    from app.database.repositories.youtube_repository import YoutubeRepository
    from app.services.digest_service import DigestService

    logger.info("[DeepVideo] Starting chunking + map-reduce phase")

    with get_db_session() as db:
        chunk_repo = ContentChunkRepository(db)
        candidates = (
            db.query(YoutubeVideo)
            .filter(YoutubeVideo.duration_seconds.isnot(None))
            .filter(YoutubeVideo.duration_seconds >= LONG_VIDEO_THRESHOLD_SECONDS)
            .filter(YoutubeVideo.transcript_segments.isnot(None))
            .all()
        )
        video_data = [
            (v.id, v.title, v.transcript_segments)
            for v in candidates
            if not chunk_repo.has_chunks("youtube_video", v.id)
        ]
        allowed_topics = TaxonomyTopicRepository(db).get_active_slugs()

    if not video_data:
        logger.info("[DeepVideo] Nothing to process")
        return

    chunk_agent = ChunkSummaryAgent()
    enrichment_agent = EnrichmentAgent(allowed_topics=allowed_topics)
    digest_service = DigestService(config=config)  # only used for its _persist_enrichment/_reembed helpers

    processed = errors = 0
    for video_id, title, segments in video_data:
        try:
            chunks = _build_transcript_chunks(segments)
            if not chunks:
                continue

            chunk_rows: List[Tuple[float, float, str, str]] = []
            summary_blurbs = []
            for start, end, seg_list in chunks:
                chunk_text = " ".join(s["text"] for s in seg_list)
                chunk_summary = chunk_agent.generate(title, chunk_text)
                if chunk_summary is None:
                    logger.warning(
                        "[DeepVideo] Chunk summary failed for video id=%d [%ds-%ds] — skipping chunk",
                        video_id, start, end,
                    )
                    continue
                chunk_rows.append((start, end, chunk_summary.chapter_title, chunk_summary.summary))
                summary_blurbs.append(f"[{int(start)}s-{int(end)}s] {chunk_summary.chapter_title}: {chunk_summary.summary}")

            if not chunk_rows:
                logger.warning("[DeepVideo] All chunks failed for video id=%d — skipping", video_id)
                errors += 1
                continue

            enrichment_output = enrichment_agent.generate(
                title=title,
                content="\n\n".join(summary_blurbs),
                article_type="chaptered YouTube video",
            )

            with get_db_session() as db:
                ContentChunkRepository(db).replace_for_content(
                    content_type="youtube_video", content_id=video_id,
                    chunks=chunk_rows, summary_version=CHUNK_SUMMARY_VERSION,
                )
                if enrichment_output is not None:
                    YoutubeRepository(db).update_summary(video_id, enrichment_output.summary)
                    digest_service._persist_enrichment(db, "youtube_video", video_id, enrichment_output)
                    digest_service._reembed(db, "youtube_video", video_id, enrichment_output.summary)
                else:
                    logger.warning(
                        "[DeepVideo] Reduce-step enrichment failed for video id=%d — chunks saved, enrichment unchanged",
                        video_id,
                    )
            processed += 1
        except Exception:
            logger.exception("[DeepVideo] Error processing video id=%d", video_id)
            errors += 1

    result.deep_video_processed = processed
    result.deep_video_errors = errors
    logger.info("[DeepVideo] Done. processed=%d errors=%d", processed, errors)


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

    # ── Step 2.5: STT dispatch (M12) ──────────────────────────────────────
    # Drains any queued stt_jobs (this run's caption-less stubs, plus any
    # left over from a previous run) onto the dedicated "stt" queue.
    if not args.dry_run:
        run_stt_dispatch_phase(result)
    else:
        logger.info("[STT] Skipped (dry-run mode)")

    # ── Step 3: embedding (Phase 1.5) ─────────────────────────────────────
    if not args.dry_run:
        logger.info("[Embedding] Starting embedding phase")
        run_embedding_phase(result)
    else:
        logger.info("[Embedding] Skipped (dry-run mode)")

    # ── Step 3: digest + email (Phase 2+3) ───────────────────────────────
    # Enrichment (M8: summary + content_category/topics/entities/etc, one
    # LLM call per item) happens INSIDE DigestService.run() as its own Step 1
    # — see app/services/digest_service.py::_enrich_unenriched().
    if args.skip_digest:
        logger.info("[Digest] Skipped (--skip-digest)")
    elif args.dry_run:
        logger.info("[Digest] Skipped (--dry-run implies no digest phase)")
    else:
        run_digest_phase(args.hours, args.dry_run, args.skip_email, result)

    # ── Step 3.2: deep video chunking + map-reduce (M12) ──────────────────
    # After digest/enrichment (upgrades the normal single-pass enrichment
    # run_digest_phase just wrote for long videos) and before clustering
    # (so clustering works off the upgraded embedding too).
    if not args.dry_run:
        run_deep_video_phase(result)
    else:
        logger.info("[DeepVideo] Skipped (dry-run mode)")

    # ── Step 3.5: clustering + quality scoring (M8) ───────────────────────
    # Run AFTER digest/enrichment so clustering works off the freshest
    # (post-enrichment) embeddings, and scoring can read the enrichment/
    # topics/entities this same run may have just produced.
    if not args.dry_run:
        run_clustering_phase(result)
        run_scoring_phase(result)
        run_trend_computation_phase(result)
    else:
        logger.info("[Clustering/Scoring/Trends] Skipped (dry-run mode)")

    # ── Step 4: print summary ─────────────────────────────────────────────
    result.print_summary()

    total_errors = (
        result.youtube_errors
        + result.articles_errors
        + len(result.digest_errors)
        + result.scoring_errors
    )
    if total_errors > 0:
        logger.warning("Pipeline completed with %d error(s)", total_errors)
        sys.exit(1)

    logger.info("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
