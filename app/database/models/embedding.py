# app/database/models/embedding.py
#
# One embedding table shared by BOTH articles and youtube_videos.
#
# Why one shared table instead of an "embedding" column on each?
# - Articles and videos both need embeddings, so this avoids duplicating
#   the same column + logic in two places.
# - content_type + content_id together point at whichever table the
#   embedding belongs to (e.g. "article", 42 or "youtube_video", 7).
#   This pattern is called a polymorphic association — normal and simple,
#   not overengineering.

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

# all-MiniLM-L6-v2 (the model we're using) always outputs a vector of 384 numbers.
# If you ever switch embedding models, this number must match the new model's output size.
EMBEDDING_DIM = 384


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="'article' or 'youtube_video'",
    )
    content_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Points to articles.id or youtube_videos.id, depending on content_type",
    )

    embedding: Mapped[list] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="all-MiniLM-L6-v2",
        comment="Which embedding model produced this vector — matters if you switch models later",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        # One embedding per item — re-embedding overwrites, never duplicates
        UniqueConstraint("content_type", "content_id", name="uq_embedding_content"),
        Index("ix_embeddings_content", "content_type", "content_id"),
    )

    def __repr__(self) -> str:
        return f"<Embedding content_type={self.content_type!r} content_id={self.content_id}>"