# app/database/models/youtube_video.py
#
# Stores YouTube video metadata + transcripts scraped by YouTubeScraper.

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class YoutubeVideo(Base):
    """
    Represents a single YouTube video with its transcript.

    Why a separate table from Article?
    - YouTube content has video-specific fields (video_id, channel_name).
    - Keeping them separate makes queries and indexes more targeted.
    - Future: you might store thumbnail_url, view_count here.
    """

    __tablename__ = "youtube_videos"

    # -------------------------------------------------------------------------
    # Primary key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="Auto-incrementing surrogate key. SQLite variant is Integer, not BigInteger -- see app/database/models/article.py's id column comment for why.",
    )

    # -------------------------------------------------------------------------
    # YouTube-specific fields
    # -------------------------------------------------------------------------

    # The 11-character YouTube video ID (e.g. "dQw4w9WgXcQ").
    # Unique at the DB level — prevents re-inserting the same video.
    video_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        comment="11-character YouTube video identifier",
    )

    channel_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable channel name from config (e.g. 'Andrej Karpathy')",
    )

    channel_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="YouTube channel ID (UC...)",
    )

    # -------------------------------------------------------------------------
    # Shared content fields (mirrors Article)
    # -------------------------------------------------------------------------
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,
        comment="Full YouTube watch URL",
    )

    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="youtube",
        comment="Always 'youtube' for this table",
    )

    # The transcript (may be auto-generated or manually created).
    # Can be NULL if the video has no transcript at all.
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Full transcript text (M7: captured in full — not truncated at scrape time)",
    )

    # One-paragraph AI summary — set by the curator agent after scraping
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    tags: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        default=None,
        comment="Comma-separated topic tags assigned by curator agent",
    )

    # -------------------------------------------------------------------------
    # Deep Media (M12) — chunked chaptered summaries + STT fallback
    # -------------------------------------------------------------------------
    transcript_segments: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        default=None,
        comment="[{start, duration, text}, ...] — per-segment timing, same shape whether sourced from YouTube captions or STT (app/services/stt_service.py). NULL for videos scraped before M12 or still pending transcription (see stt_jobs).",
    )
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Video length — derived from transcript_segments' last entry (captions) or yt-dlp metadata (STT). Drives both the STT duration ceiling and the long-video tier gate (run_pipeline.py's run_deep_video_phase).",
    )

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Video upload date from YouTube RSS feed",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # -------------------------------------------------------------------------
    # Indexes
    # -------------------------------------------------------------------------
    __table_args__ = (
        Index("ix_youtube_videos_published_at", "published_at"),
        Index("ix_youtube_videos_channel_name", "channel_name"),
        Index(
            "ix_youtube_videos_summary_null",
            "id",
            postgresql_where="summary IS NULL",
        ),
        UniqueConstraint("video_id", name="uq_youtube_videos_video_id"),
        UniqueConstraint("url",      name="uq_youtube_videos_url"),
    )

    def __repr__(self) -> str:
        return (
            f"<YoutubeVideo id={self.id} video_id={self.video_id!r} "
            f"channel={self.channel_name!r} title={self.title[:50]!r}>"
        )

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "video_id":     self.video_id,
            "channel_name": self.channel_name,
            "title":        self.title,
            "url":          self.url,
            "source":       self.source,
            "summary":      self.summary,
            "tags":         self.tags,
            "duration_seconds": self.duration_seconds,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at":   self.created_at.isoformat()   if self.created_at   else None,
        }