# app/database/repositories/content_entity_repository.py

import logging
from typing import List, Tuple

from app.database.models.content_entity import ContentEntity
from app.database.repositories.base_repository import BaseRepository
from app.database.repositories.entity_repository import EntityRepository

logger = logging.getLogger(__name__)


class ContentEntityRepository(BaseRepository[ContentEntity]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentEntity)
        self._entities = EntityRepository(db)

    def get_content_for_entity(self, entity_id: int) -> List[Tuple[str, int]]:
        """
        Reverse lookup (M10): every (content_type, content_id) that mentions
        this entity — "who's talking about this person/company/model".
        Used for person-follow mention surfacing and any future
        alert-style consumer.
        """
        return (
            self.db.query(ContentEntity.content_type, ContentEntity.content_id)
            .filter(ContentEntity.entity_id == entity_id)
            .all()
        )

    def replace_for_content(
        self, content_type: str, content_id: int, entities: List[Tuple[str, str]],
    ) -> int:
        """
        Wholesale-replace one item's entity mentions. `entities` is a list of
        (name, entity_type) pairs — each is get_or_created against the
        deduplicated `entities` table before the join row is written.
        """
        self.db.query(ContentEntity).filter(
            ContentEntity.content_type == content_type, ContentEntity.content_id == content_id,
        ).delete()

        rows = []
        seen_entity_ids = set()
        for name, entity_type in entities:
            if not name or not name.strip():
                continue
            entity = self._entities.get_or_create(name.strip(), entity_type)
            if entity.id in seen_entity_ids:
                continue  # same entity mentioned twice in one item — one join row is enough
            seen_entity_ids.add(entity.id)
            rows.append(ContentEntity(content_type=content_type, content_id=content_id, entity_id=entity.id))

        if rows:
            self.db.add_all(rows)
        self.db.commit()
        return len(rows)
