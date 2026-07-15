# app/database/models/content_topic.py
#
# Join table: which taxonomy_topics a given content item was tagged with by
# EnrichmentAgent's structured LLM call (M8). content_type/content_id follow
# the same polymorphic-association convention as Embedding/UserRanking/etc
# ("article" | "youtube_video" + the real PK on that table).
#
# Written wholesale-replace per item at enrichment time (an item's topics can
# be re-tagged if re-enriched under a newer enrichment_version) — see
# ContentTopicRepository.replace_for_content().

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentTopic(Base):
    __tablename__ = "content_topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    taxonomy_topic_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("taxonomy_topics.id"), nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "taxonomy_topic_id", name="uq_content_topic"),
        Index("ix_content_topics_content", "content_type", "content_id"),
        Index("ix_content_topics_topic", "taxonomy_topic_id"),
    )

    def __repr__(self) -> str:
        return f"<ContentTopic {self.content_type}:{self.content_id} topic_id={self.taxonomy_topic_id}>"
