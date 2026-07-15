# app/database/models/content_score.py
#
# Quality score v1 (heuristic) PLUS a snapshot of the exact feature vector
# that produced it (Architecture Principle 7: "log features now so they
# become future ML training data" — the point is the features, not just the
# score). Upserted per item each scoring run — see
# app/database/repositories/content_score_repository.py.
#
# `features` reserves a "popularity" key from day one (None until the
# [Nice-to-have] popularity re-fetch job ships) — JSONB has no migration
# cost to reserving the key path now, and Principle 7 favors logging the
# shape early even before every feature has real data.

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentScore(Base):
    __tablename__ = "content_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_version: Mapped[str] = mapped_column(String(50), nullable=False)
    features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Exact feature vector that produced `score` — the point of this table per Principle 7, not just the score itself",
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", name="uq_content_score"),
    )

    def __repr__(self) -> str:
        return f"<ContentScore {self.content_type}:{self.content_id} score={self.score:.3f}>"
