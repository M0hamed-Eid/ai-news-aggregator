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


def _derive_duration_seconds(segments: Optional[list]) -> Optional[int]:
    """Video length from its last transcript segment's end (start + duration). None if no segments yet."""
    if not segments:
        return None
    last = segments[-1]
    return round(last["start"] + last["duration"])


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
            video_id            = scraped.video_id or "",
            channel_name        = scraped.channel_or_author,
            channel_id          = scraped.channel_id,
            title               = scraped.title,
            url                 = scraped.url,
            source              = "youtube",
            content             = scraped.content or None,
            published_at        = _ensure_tz(scraped.published_at),
            transcript_segments = scraped.transcript_segments,
            duration_seconds    = _derive_duration_seconds(scraped.transcript_segments),
        )
        self.db.add(video)
        self.db.flush()
        if not scraped.content:
            self._queue_stt(content_id=video.id)
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
                "video_id":            item.video_id or "",
                "channel_name":        item.channel_or_author,
                "channel_id":          item.channel_id,
                "title":               item.title,
                "url":                 item.url,
                "source":              "youtube",
                "content":             item.content or None,
                "published_at":        _ensure_tz(item.published_at),
                "transcript_segments": item.transcript_segments,
                "duration_seconds":    _derive_duration_seconds(item.transcript_segments),
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
            .returning(YoutubeVideo.id, YoutubeVideo.content)
        )

        result        = self.db.execute(stmt)
        inserted_rows = result.fetchall()
        inserted      = len(inserted_rows)
        skipped       = len(scraped_list) - inserted

        # M12: every inserted video with no content is caption-less — queue
        # it for STT (app/tasks/stt_tasks.py). Queuing here (same transaction
        # as the insert) rather than dispatching a Celery task here avoids
        # racing the outer get_db_session() commit; a later pipeline phase
        # drains SttJobRepository.get_queued() and dispatches once these rows
        # are safely committed.
        for row in inserted_rows:
            if not row.content:
                self._queue_stt(content_id=row.id)

        logger.info(
            f"Bulk insert videos: {inserted} inserted, {skipped} skipped (duplicates)"
        )
        return (inserted, skipped)

    def _queue_stt(self, content_id: int) -> None:
        from app.database.repositories.stt_job_repository import SttJobRepository
        SttJobRepository(self.db).upsert_status(
            content_type="youtube_video", content_id=content_id, status="queued",
        )
        logger.info(f"Queued STT for youtube_video id={content_id} (no captions)")

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

    def get_unenriched(self, limit: int = 20) -> List[YoutubeVideo]:
        """
        Return videos with no content_enrichment row yet (M8) — see
        ArticleRepository.get_unenriched()'s docstring for why this replaces
        get_unsummarised() as the enrichment-phase driver.
        """
        from app.database.models.content_enrichment import ContentEnrichment

        enriched_ids = self.db.query(ContentEnrichment.content_id).filter(
            ContentEnrichment.content_type == "youtube_video"
        )
        return (
            self.db.query(YoutubeVideo)
            .filter(~YoutubeVideo.id.in_(enriched_ids))
            .filter(YoutubeVideo.content.isnot(None))  # no point enriching empty transcripts
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

    def get_by_ids(self, ids: List[int]) -> List[YoutubeVideo]:
        """Bulk-fetch by primary key — used to rehydrate a ranked id list (M9) into real rows."""
        if not ids:
            return []
        return self.db.query(YoutubeVideo).filter(YoutubeVideo.id.in_(ids)).all()

    def get_missing_transcript_segments(self, limit: int = 20) -> List[YoutubeVideo]:
        """
        M12 backfill target: videos scraped before the segment-capture fix
        (app/database/backfill_transcript_segments.py). Restricted to
        content.isnot(None) because every pre-M12 row necessarily has real
        content — caption-less videos were dropped entirely before this
        milestone, never stored with empty content.
        """
        return (
            self.db.query(YoutubeVideo)
            .filter(YoutubeVideo.transcript_segments.is_(None))
            .filter(YoutubeVideo.content.isnot(None))
            .order_by(YoutubeVideo.published_at.desc())
            .limit(limit)
            .all()
        )


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt