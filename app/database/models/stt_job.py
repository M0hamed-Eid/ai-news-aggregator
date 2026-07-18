# app/database/models/stt_job.py
#
# STT job status/metadata (M12 — Deep Media), one row per content item —
# upserted, not appended, same convention as ContentEnrichment/ContentScore.
# Written for EVERY YoutubeVideo, not just ones that actually needed STT:
# `transcript_source` is the one authoritative answer to "how did this
# video get its transcript" (manual_caption / auto_caption / stt), and
# `status` tracks the STT pipeline's own lifecycle for the residue that
# needed it. A video whose captions worked gets a row with
# transcript_source set and status='completed' at scrape time, purely for
# that single-source-of-truth property — not because STT ever ran for it.

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SttJob(Base):
    __tablename__ = "stt_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video' — in practice only 'youtube_video' today")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued",
        comment="'queued' | 'running' | 'completed' | 'failed' | 'skipped_too_long'",
    )
    transcript_source: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None,
        comment="'manual_caption' | 'auto_caption' | 'stt' — set for every video regardless of which path produced its transcript",
    )
    whisper_model: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", name="uq_stt_jobs_content"),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'skipped_too_long')",
            name="ck_stt_jobs_status",
        ),
        CheckConstraint(
            "transcript_source IS NULL OR transcript_source IN ('manual_caption', 'auto_caption', 'stt')",
            name="ck_stt_jobs_transcript_source",
        ),
    )

    def __repr__(self) -> str:
        return f"<SttJob {self.content_type}:{self.content_id} status={self.status!r} source={self.transcript_source!r}>"
