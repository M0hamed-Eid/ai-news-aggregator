# app/database/repositories/content_enrichment_repository.py

import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.content_enrichment import ContentEnrichment
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ContentEnrichmentRepository(BaseRepository[ContentEnrichment]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentEnrichment)

    def upsert(
        self,
        content_type: str,
        content_id: int,
        content_category: str,
        technical_depth: int,
        key_points: list,
        technical_details: str,
        business_angle: str,
        why_it_matters: str,
        enrichment_version: str,
    ) -> ContentEnrichment:
        values = {
            "content_type": content_type,
            "content_id": content_id,
            "content_category": content_category,
            "technical_depth": technical_depth,
            "key_points": key_points,
            "technical_details": technical_details,
            "business_angle": business_angle,
            "why_it_matters": why_it_matters,
            "enrichment_version": enrichment_version,
        }
        stmt = (
            pg_insert(ContentEnrichment)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["content_type", "content_id"],
                set_={k: v for k, v in values.items() if k not in ("content_type", "content_id")},
            )
            .returning(ContentEnrichment)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def exists_for(self, content_type: str, content_id: int) -> bool:
        return (
            self.db.query(ContentEnrichment)
            .filter(ContentEnrichment.content_type == content_type, ContentEnrichment.content_id == content_id)
            .count()
        ) > 0
