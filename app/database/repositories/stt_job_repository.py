# app/database/repositories/stt_job_repository.py

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.stt_job import SttJob
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SttJobRepository(BaseRepository[SttJob]):

    def __init__(self, db) -> None:
        super().__init__(db, SttJob)

    def upsert_status(
        self, content_type: str, content_id: int, *, status: str,
        transcript_source: Optional[str] = None, whisper_model: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> SttJob:
        """
        One row per (content_type, content_id) — written at scrape time
        (transcript_source='manual_caption'/'auto_caption', status='completed')
        for every video whose captions worked, and progressed through
        queued -> running -> completed/failed for the residue that needs
        real STT (app/tasks/stt_tasks.py).
        """
        now = datetime.now(timezone.utc)
        values = {
            "content_type": content_type, "content_id": content_id, "status": status,
            "transcript_source": transcript_source, "whisper_model": whisper_model,
            "error_message": error_message,
        }
        if status == "running":
            values["started_at"] = now
        elif status in ("completed", "failed"):
            values["completed_at"] = now

        stmt = (
            pg_insert(SttJob)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["content_type", "content_id"],
                set_={k: v for k, v in values.items() if k not in ("content_type", "content_id")},
            )
            .returning(SttJob)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_for_content(self, content_type: str, content_id: int) -> Optional[SttJob]:
        return (
            self.db.query(SttJob)
            .filter(SttJob.content_type == content_type, SttJob.content_id == content_id)
            .first()
        )

    def get_queued(self, limit: int = 20) -> List[SttJob]:
        return (
            self.db.query(SttJob)
            .filter(SttJob.status == "queued")
            .order_by(SttJob.requested_at.asc())
            .limit(limit)
            .all()
        )
