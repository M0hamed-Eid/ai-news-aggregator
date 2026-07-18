# app/database/repositories/trend_report_repository.py

import logging
from datetime import date as date_type
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.trend_report import TrendReport
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TrendReportRepository(BaseRepository[TrendReport]):

    def __init__(self, db) -> None:
        super().__init__(db, TrendReport)

    def upsert_for_week(
        self, *, week_start_date: date_type, narrative: list, raw_narrative: list,
        narrative_version: str, llm_model: str,
    ) -> TrendReport:
        """One report per week — re-generating an already-covered week
        replaces it rather than duplicating."""
        values = {
            "week_start_date": week_start_date, "narrative": narrative,
            "raw_narrative": raw_narrative, "narrative_version": narrative_version,
            "llm_model": llm_model,
        }
        stmt = (
            pg_insert(TrendReport)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["week_start_date"],
                set_={
                    "narrative": narrative, "raw_narrative": raw_narrative,
                    "narrative_version": narrative_version, "llm_model": llm_model,
                },
            )
            .returning(TrendReport)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_latest(self) -> Optional[TrendReport]:
        return self.db.query(TrendReport).order_by(TrendReport.week_start_date.desc()).first()
