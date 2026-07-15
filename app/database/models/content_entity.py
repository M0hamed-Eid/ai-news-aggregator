# app/database/models/content_entity.py
#
# Join table: which entities were mentioned in a given content item (M8),
# written wholesale-replace per item at enrichment time — see
# ContentEntityRepository.replace_for_content().

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentEntity(Base):
    __tablename__ = "content_entities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    entity_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("entities.id"), nullable=False)
    mention_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "entity_id", name="uq_content_entity"),
        Index("ix_content_entities_content", "content_type", "content_id"),
        Index("ix_content_entities_entity", "entity_id"),
    )

    def __repr__(self) -> str:
        return f"<ContentEntity {self.content_type}:{self.content_id} entity_id={self.entity_id}>"
