# app/database/models/user_affinity.py
#
# Per-user affinity weights derived from behavioral events (M7). Written by
# the nightly aggregation Celery task (app/tasks/affinity_tasks.py) from raw
# user_events (Django-owned, read via app/database/models/django_readmodels.py's
# DjangoUserEvent mirror); read by the future ranking process (M9).
#
# dimension/key is a generic (kind, value) pair so the same table serves
# topic/source/entity affinities without a schema change per dimension.
# Only "source" produces real rows until M8 ships topic/entity taxonomy —
# that's a data-availability gap, not a schema gap, so the table supports
# all three dimensions from day one.
#
# user_id is a plain reference to Django's users.id, same convention as
# UserRanking.user_id / DigestLog.user_id — no real cross-ORM FK.

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserAffinity(Base):
    __tablename__ = "user_affinities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Django users.id — plain reference, no DB-level FK (different ORM/metadata)",
    )

    dimension: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="'topic' | 'source' | 'entity' — only 'source' is populated until M8's taxonomy exists",
    )
    key: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="The dimension's value, e.g. a Source.key when dimension='source'",
    )
    weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="Time-decayed affinity weight, recomputed wholesale per (user, dimension, key) each nightly run",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "dimension", "key", name="uq_user_affinity_dimension_key"),
        Index("ix_user_affinities_user_dimension", "user_id", "dimension"),
        CheckConstraint("dimension IN ('topic', 'source', 'entity')", name="ck_user_affinities_dimension"),
    )

    def __repr__(self) -> str:
        return f"<UserAffinity user_id={self.user_id} {self.dimension}={self.key!r} weight={self.weight:.3f}>"
