# app/database/repositories/content_score_repository.py

import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.content_score import ContentScore
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ContentScoreRepository(BaseRepository[ContentScore]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentScore)

    def upsert(
        self, content_type: str, content_id: int, score: float, score_version: str, features: dict,
    ) -> ContentScore:
        values = {
            "content_type": content_type,
            "content_id": content_id,
            "score": score,
            "score_version": score_version,
            "features": features,
        }
        stmt = (
            pg_insert(ContentScore)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["content_type", "content_id"],
                set_={"score": score, "score_version": score_version, "features": features},
            )
            .returning(ContentScore)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()
