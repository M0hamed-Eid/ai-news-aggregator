# app/database/models/content_chunk.py
#
# Chunk-level chaptered summaries (M12 — Deep Media), one row per ~10-minute
# chunk of a long video's transcript. Real child table (not a JSONB list),
# same "queried/rendered per-row" convention as ContentEntity/ContentTopic/
# ContentClusterMember — the frontend renders each chunk as its own
# timestamp-linked chapter card. Written by run_pipeline.py's
# run_deep_video_phase() (the "map" step of chunked map-reduce
# summarization — see app/agents/chunk_summary_agent.py for the "why a
# separate, smaller schema than EnrichmentOutput" reasoning), wholesale
# replaced per item if it's ever re-chunked (matches ContentCluster's
# "replace, don't accumulate" discipline), never appended to.

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video' — in practice only 'youtube_video' produces chunks today")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="0-based order within this item's chunks")
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)

    chapter_title: Mapped[str] = mapped_column(String(200), nullable=False)
    chunk_summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_version: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Prompt/schema version tag (app/agents/chunk_summary_agent.py's CHUNK_SUMMARY_VERSION)",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "chunk_index", name="uq_content_chunks_content_index"),
        Index("ix_content_chunks_content", "content_type", "content_id"),
    )

    def __repr__(self) -> str:
        return f"<ContentChunk {self.content_type}:{self.content_id} #{self.chunk_index} [{self.start_seconds:.0f}-{self.end_seconds:.0f}s]>"
