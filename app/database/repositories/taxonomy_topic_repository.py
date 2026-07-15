# app/database/repositories/taxonomy_topic_repository.py

import logging
from typing import Set

from app.database.models.taxonomy_topic import TaxonomyTopic
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TaxonomyTopicRepository(BaseRepository[TaxonomyTopic]):

    def __init__(self, db) -> None:
        super().__init__(db, TaxonomyTopic)

    def get_by_slug(self, slug: str):
        return self.db.query(TaxonomyTopic).filter(TaxonomyTopic.slug == slug).first()

    def get_active_slugs(self) -> Set[str]:
        """The live controlled vocabulary — EnrichmentAgent validates every
        LLM-returned topic slug against this set before persisting."""
        rows = self.db.query(TaxonomyTopic.slug).filter(TaxonomyTopic.is_active.is_(True)).all()
        return {slug for (slug,) in rows}
