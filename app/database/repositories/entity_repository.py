# app/database/repositories/entity_repository.py

import logging

from app.database.models.entity import Entity
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class EntityRepository(BaseRepository[Entity]):

    def __init__(self, db) -> None:
        super().__init__(db, Entity)

    def get_or_create(self, name: str, entity_type: str) -> Entity:
        entity = (
            self.db.query(Entity)
            .filter(Entity.name == name, Entity.entity_type == entity_type)
            .first()
        )
        if entity is not None:
            return entity
        entity = Entity(name=name, entity_type=entity_type)
        self.db.add(entity)
        self.db.flush()  # populate entity.id without committing yet — caller controls the transaction
        return entity
