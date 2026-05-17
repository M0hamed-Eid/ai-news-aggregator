# app/database/repositories/youtube_repository.py

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models.youtube_video import YoutubeVideo
from app.database.repositories.base_repository import BaseRepository
from app.scrapers.base_scraper import ScrapedArticle

logger = logging.getLogger(__name__)


class YoutubeRepository(BaseRepository[YoutubeVideo]):

    def __init__(self, db: Session) -> None:
        super().__init__(db, YoutubeVideo)

    # =========================================================================
    # Single-record operations
    # =========================================================================

    def exists_by_video_id(self, video_id: str) -> bool:
        """True if a video with this YouTube ID is already stored."""
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.video_id == video_id)
            .count()
        ) > 0

    def get_by_video_id(self, video_id: str) -> Optional[YoutubeVideo]:
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.video_id == video_id)
            .first()
        )

    def create(self, scraped: ScrapedArticle) -> Optional[YoutubeVideo]:
        """
        Insert one video.
        Returns the new YoutubeVideo, or None if it already exists.
        """
        if scraped.video_id and self.exists_by_video_id(scraped.video_id):
            logger.debug(f"Video already exists, skipping: {scraped.video_id}")
            return None

        video = YoutubeVideo(
            video_id     = scraped.video_id or "",
            channel_name = scraped.channel_or_author,
            title        = scraped.title,
            url          = scraped.url,
            source       = "youtube",
            content      = scraped.content or None,
            published_at = _ensure_tz(scraped.published_at),
        )
        self.db.add(video)
        self.db.flush()
        logger.info(f"Inserted video id={video.id}: {video.title[:60]}")
        return video

    def update_summary(self, video_id_pk: int, summary: str, tags: str = "") -> bool:
        """Update AI summary + tags. video_id_pk is the DB integer PK (not YouTube ID)."""
        video = self.get_by_id(video_id_pk)
        if video is None:
            logger.warning(f"update_summary: YoutubeVideo id={video_id_pk} not found")
            return False
        video.summary    = summary
        video.tags       = tags
        video.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        logger.info(f"Updated summary for video id={video_id_pk}")
        return True

    # =========================================================================
    # Bulk operations
    # =========================================================================

    def bulk_create(self, scraped_list: List[ScrapedArticle]) -> Tuple[int, int]:
        """
        Bulk-insert videos with ON CONFLICT DO NOTHING on video_id.
        Returns (inserted_count, skipped_count).
        """
        if not scraped_list:
            return (0, 0)

        rows = [
            {
                "video_id":     item.video_id or "",
                "channel_name": item.channel_or_author,
                "title":        item.title,
                "url":          item.url,
                "source":       "youtube",
                "content":      item.content or None,
                "published_at": _ensure_tz(item.published_at),
            }
            for item in scraped_list
            if item.video_id  # skip entries without a video_id
        ]

        if not rows:
            return (0, len(scraped_list))

        stmt = (
            pg_insert(YoutubeVideo)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["video_id"])
        )

        result   = self.db.execute(stmt)
        inserted = result.rowcount
        skipped  = len(scraped_list) - inserted

        logger.info(
            f"Bulk insert videos: {inserted} inserted, {skipped} skipped (duplicates)"
        )
        return (inserted, skipped)

    # =========================================================================
    # Query helpers
    # =========================================================================

    def get_by_channel(self, channel_name: str, limit: int = 20) -> List[YoutubeVideo]:
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.channel_name == channel_name)
            .order_by(YoutubeVideo.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_unsummarised(self, limit: int = 20) -> List[YoutubeVideo]:
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.summary.is_(None))
            .filter(YoutubeVideo.content.isnot(None))  # no point summarising empty transcripts
            .order_by(YoutubeVideo.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_recent(self, hours: int = 24, limit: int = 100) -> List[YoutubeVideo]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.published_at >= cutoff)
            .order_by(YoutubeVideo.published_at.desc())
            .limit(limit)
            .all()
        )


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt