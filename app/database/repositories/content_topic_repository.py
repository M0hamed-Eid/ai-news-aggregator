# app/database/repositories/content_topic_repository.py

import logging
from typing import List

from app.database.models.content_topic import ContentTopic
from app.database.models.taxonomy_topic import TaxonomyTopic
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ContentTopicRepository(BaseRepository[ContentTopic]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentTopic)

    def replace_for_content(self, content_type: str, content_id: int, topic_slugs: List[str]) -> int:
        """
        Wholesale-replace one item's topic tags — an item's topics can shift
        if re-enriched under a newer enrichment_version. `topic_slugs` must
        already be validated against the live taxonomy_topics vocabulary by
        the caller (EnrichmentAgent) — unknown slugs here are silently
        skipped rather than raising, since that validation already happened.
        """
        self.db.query(ContentTopic).filter(
            ContentTopic.content_type == content_type, ContentTopic.content_id == content_id,
        ).delete()

        if not topic_slugs:
            self.db.commit()
            return 0

        slug_to_id = dict(
            self.db.query(TaxonomyTopic.slug, TaxonomyTopic.id)
            .filter(TaxonomyTopic.slug.in_(topic_slugs))
            .all()
        )
        rows = [
            ContentTopic(content_type=content_type, content_id=content_id, taxonomy_topic_id=topic_id)
            for slug, topic_id in slug_to_id.items()
        ]
        if rows:
            self.db.add_all(rows)
        self.db.commit()
        return len(rows)
