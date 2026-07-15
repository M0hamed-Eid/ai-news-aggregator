# app/database/models/user_profile_vector.py
#
# One row per user: a decayed weighted mean of the embeddings of items that
# user has engaged with (click/save/dwell — see app/tasks/ranking_tasks.py
# for the exact weighting, which reuses affinity_tasks.py's EVENT_WEIGHTS).
# This is the "taste vector" the two-stage ranker's candidate-generation
# stage does a pgvector nearest-neighbor search against (Milestone 9).
#
# Pipeline-owned: the ranking process computes and reads this, same
# ownership rule as user_rankings/user_affinities (Django never writes it).
#
# `sample_size` records how many engagement events actually contributed —
# 0 means "cold start, no real engagement yet" so callers know to fall back
# to an onboarding-interest-derived vector instead of trusting an all-zero
# or stale vector silently (see ranking_service.py's cold-start handling).

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.embedding import EMBEDDING_DIM


class UserProfileVector(Base):
    __tablename__ = "user_profile_vectors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True,
        comment="Django users.id — plain reference, no DB-level FK (different ORM/metadata)",
    )

    vector: Mapped[list] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="all-MiniLM-L6-v2",
        comment="Which embedding model produced the source vectors this mean was built from",
    )

    sample_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="How many engagement events contributed to this vector — 0 means cold start (no engagement yet)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_profile_vector_user"),
    )

    def __repr__(self) -> str:
        return f"<UserProfileVector user_id={self.user_id} sample_size={self.sample_size}>"
