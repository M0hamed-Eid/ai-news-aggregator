# app/database/repositories/trend_repository.py

import logging
from datetime import date as date_type
from typing import List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.trend import Trend
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TrendRepository(BaseRepository[Trend]):

    def __init__(self, db) -> None:
        super().__init__(db, Trend)

    def upsert_daily(
        self, *, dimension: str, key: str, date: date_type, mention_count: int,
        baseline_mean: float, baseline_stddev: float, z_score: Optional[float], is_trending: bool,
    ) -> Trend:
        """One row per (dimension, key, date) — re-run-safe (upserted, not
        appended) so run_trend_computation_phase can recompute "today"'s row
        every 6h as the day progresses without creating duplicates."""
        values = {
            "dimension": dimension, "key": key, "date": date,
            "mention_count": mention_count, "baseline_mean": baseline_mean,
            "baseline_stddev": baseline_stddev, "z_score": z_score, "is_trending": is_trending,
        }
        stmt = (
            pg_insert(Trend)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["dimension", "key", "date"],
                set_={
                    "mention_count": mention_count, "baseline_mean": baseline_mean,
                    "baseline_stddev": baseline_stddev, "z_score": z_score, "is_trending": is_trending,
                },
            )
            .returning(Trend)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_history(self, dimension: str, key: str, start_date: date_type, end_date: date_type) -> List[Trend]:
        """Already-persisted rows in [start_date, end_date] — the baseline
        computation reads history back from here rather than recomputing
        historical days from the raw corpus every run."""
        return (
            self.db.query(Trend)
            .filter(Trend.dimension == dimension, Trend.key == key)
            .filter(Trend.date >= start_date, Trend.date <= end_date)
            .order_by(Trend.date.asc())
            .all()
        )

    def get_mentioned_entity_ids(self) -> List[int]:
        """Distinct entity_ids that appear in content_entities at all — the
        entity-dimension iteration set (not the full `entities` table, most
        of which is never mentioned in any given window)."""
        from app.database.models.content_entity import ContentEntity
        return [eid for (eid,) in self.db.query(ContentEntity.entity_id).distinct().all()]
