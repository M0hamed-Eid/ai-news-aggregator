# app/database/models/trend.py
#
# Daily burst-detection time-series (M11) — one row per (dimension, key, date).
# Written by run_pipeline.py's run_trend_computation_phase(), which runs as
# the 6th phase of the existing 6-hourly pipeline chain (no separate beat
# schedule — see that function's docstring for why). Deliberately the ONLY
# table for this milestone's "trends"/"entity_timelines" roadmap items: an
# entity page's timeline is just `Trend.objects.filter(dimension='entity',
# key=str(entity_id))` against the index below — a second "materialized"
# table would duplicate this one's write path for zero query benefit
# (same single-source-of-truth discipline as ContentScore).
#
# dimension is deliberately narrower than UserAffinity's 3-way vocabulary —
# 'topic' | 'entity' only, never 'source': a source publishes, it doesn't
# "spike" the way a topic/entity's mention frequency can. `key` follows the
# same per-type string-key convention as UserAffinity.key / UserFollow.target_key
# (TaxonomyTopic.slug for 'topic', str(Entity.id) for 'entity' — Entity has no slug).
#
# Cluster-size velocity (the roadmap's other named "Trending v1" signal) is
# deliberately NOT in this table — ContentCluster ids churn between pipeline
# runs (see that model's own docstring), so a 30-day trailing baseline keyed
# by cluster id would be comparing unrelated buckets across days. It's
# computed live instead (see catalog/services.py::get_hot_clusters on the
# Django side).

from datetime import date as date_type, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Trend(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    dimension: Mapped[str] = mapped_column(String(20), nullable=False, comment="'topic' | 'entity'")
    key: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="TaxonomyTopic.slug for 'topic', str(Entity.id) for 'entity'",
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, comment="UTC calendar day this row covers")

    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="Distinct content items mentioning this topic/entity, published on `date`")
    baseline_mean: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_stddev: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    z_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="NULL means insufficient history/volume to judge (see run_trend_computation_phase's guards) — never a fabricated number",
    )
    is_trending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("dimension", "key", "date", name="uq_trends_dimension_key_date"),
        Index("ix_trends_dimension_key_date", "dimension", "key", "date"),
        Index("ix_trends_date_is_trending", "date", "is_trending"),
        CheckConstraint("dimension IN ('topic', 'entity')", name="ck_trends_dimension"),
    )

    def __repr__(self) -> str:
        return f"<Trend {self.dimension}={self.key!r} date={self.date} count={self.mention_count} z={self.z_score}>"
