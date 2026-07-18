# app/database/repositories/person_entity_repository.py

import logging
from typing import List, Optional

from app.database.models.person_entity import PersonEntity
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class PersonEntityRepository(BaseRepository[PersonEntity]):

    def __init__(self, db) -> None:
        super().__init__(db, PersonEntity)

    def get_for_entity(self, entity_id: int) -> List[PersonEntity]:
        """All registered footprints for one person (usually 0-4 rows — one per footprint_type)."""
        return self.db.query(PersonEntity).filter(PersonEntity.entity_id == entity_id).all()

    def get_by_entity_and_type(self, entity_id: int, footprint_type: str) -> Optional[PersonEntity]:
        return (
            self.db.query(PersonEntity)
            .filter(PersonEntity.entity_id == entity_id, PersonEntity.footprint_type == footprint_type)
            .first()
        )

    def upsert(
        self, entity_id: int, footprint_type: str, external_identifier: str, source_id: Optional[int] = None,
    ) -> PersonEntity:
        """Insert or update this person's footprint of the given type — one row per (entity, footprint_type)."""
        existing = self.get_by_entity_and_type(entity_id, footprint_type)
        if existing is not None:
            existing.external_identifier = external_identifier
            if source_id is not None:
                existing.source_id = source_id
            self.db.commit()
            self.db.refresh(existing)
            return existing

        row = PersonEntity(
            entity_id=entity_id, footprint_type=footprint_type,
            external_identifier=external_identifier, source_id=source_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
