# app/database/repositories/article_repository.py
#
# Handles all database operations for blog articles (OpenAI + Anthropic).
#
# Design principles:
# - Every public method receives a ScrapedArticle (or a list) and returns
#   a proper model instance or a typed result. No raw SQL leaks outside.
# - Duplicate prevention is done at the DB level (unique constraint on url)
#   AND at the application level (exists_by_url check) for better error msgs.
# - Bulk insertion uses PostgreSQL's "INSERT ... ON CONFLICT DO NOTHING"
#   for maximum throughput without crashing on duplicates.

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models.article import Article
from app.database.repositories.base_repository import BaseRepository
from app.scrapers.base_scraper import ScrapedArticle

logger = logging.getLogger(__name__)


class ArticleRepository(BaseRepository[Article]):

    def __init__(self, db: Session) -> None:
        super().__init__(db, Article)

    # =========================================================================
    # Single-record operations
    # =========================================================================

    def exists_by_url(self, url: str) -> bool:
        """
        Check if an article with this URL is already in the database.
        Cheaper than a full SELECT — uses a COUNT query.
        """
        count = (
            self.db.query(Article)
            .filter(Article.url == url)
            .count()
        )
        return count > 0

    def get_by_url(self, url: str) -> Optional[Article]:
        """Fetch a single article by its canonical URL."""
        return (
            self.db.query(Article)
            .filter(Article.url == url)
            .first()
        )

    def create(self, scraped: ScrapedArticle) -> Optional[Article]:
        """
        Insert one article.
        Returns the new Article object, or None if the URL already exists.

        We check before inserting so we can give a clear log message instead
        of catching a UniqueViolation exception from the DB driver.
        """
        if self.exists_by_url(scraped.url):
            logger.debug(f"Article already exists, skipping: {scraped.url}")
            return None

        article = Article(
            title        = scraped.title,
            url          = scraped.url,
            source       = scraped.source,
            author       = scraped.channel_or_author,
            content      = scraped.content,
            published_at = _ensure_tz(scraped.published_at),
        )
        self.db.add(article)
        self.db.flush()   # flush assigns the auto-increment ID without committing
        logger.info(f"Inserted article id={article.id}: {article.title[:60]}")
        return article

    def update_summary(self, article_id: int, summary: str, tags: str = "") -> bool:
        """
        Update the AI-generated summary (and optional tags) on an existing article.
        Called by the curator agent after it has processed the article.
        Returns True if the record was found and updated, False otherwise.
        """
        article = self.get_by_id(article_id)
        if article is None:
            logger.warning(f"update_summary: Article id={article_id} not found")
            return False

        article.summary    = summary
        article.tags       = tags
        article.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info(f"Updated summary for article id={article_id}")
        return True

    # =========================================================================
    # Bulk operations
    # =========================================================================

    def bulk_create(self, scraped_list: List[ScrapedArticle]) -> Tuple[int, int]:
        """
        Insert many articles at once.

        Uses PostgreSQL's INSERT ... ON CONFLICT DO NOTHING so that duplicate
        URLs are silently skipped — no exception, no rollback.

        Returns:
            (inserted_count, skipped_count)

        Why not a loop of create()?
        A loop makes N round-trips to the DB.
        Bulk insert makes ONE round-trip regardless of N, which is much faster
        when scraping dozens of articles at once.
        """
        if not scraped_list:
            return (0, 0)

        rows = [
            {
                "title":        item.title,
                "url":          item.url,
                "source":       item.source,
                "author":       item.channel_or_author,
                "content":      item.content,
                "published_at": _ensure_tz(item.published_at),
            }
            for item in scraped_list
        ]

        # pg_insert = PostgreSQL-specific INSERT that supports ON CONFLICT
        stmt = (
            pg_insert(Article)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["url"])
        )

        result = self.db.execute(stmt)
        inserted = result.rowcount   # rows actually inserted
        skipped  = len(rows) - inserted

        logger.info(
            f"Bulk insert articles: {inserted} inserted, {skipped} skipped (duplicates)"
        )
        return (inserted, skipped)

    # =========================================================================
    # Query helpers
    # =========================================================================

    def get_by_source(self, source: str, limit: int = 50) -> List[Article]:
        """Return recent articles from a given source ('blog_openai', etc.)."""
        return (
            self.db.query(Article)
            .filter(Article.source == source)
            .order_by(Article.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_unsummarised(self, limit: int = 20) -> List[Article]:
        """
        Return articles that don't have a summary yet.
        Used by the curator agent to decide what to process next.
        """
        return (
            self.db.query(Article)
            .filter(Article.summary.is_(None))
            .order_by(Article.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(self, hours: int = 24, limit: int = 100) -> List[Article]:
        """Return articles published in the last N hours."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return (
            self.db.query(Article)
            .filter(Article.published_at >= cutoff)
            .order_by(Article.published_at.desc())
            .limit(limit)
            .all()
        )


# =============================================================================
# Helpers
# =============================================================================

def _ensure_tz(dt: datetime) -> datetime:
    """
    Make sure a datetime is timezone-aware (UTC).
    Some scrapers return naive datetimes — this fixes them before DB insertion.
    Storing timezone-naive datetimes in a TIMESTAMPTZ column causes an error.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt