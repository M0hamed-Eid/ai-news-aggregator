# app/database/repositories/embedding_repository.py

import logging
from typing import List, Optional, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models.embedding import Embedding
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class EmbeddingRepository(BaseRepository[Embedding]):

    def __init__(self, db: Session) -> None:
        super().__init__(db, Embedding)

    def exists_for(self, content_type: str, content_id: int) -> bool:
        return (
            self.db.query(Embedding)
            .filter(Embedding.content_type == content_type, Embedding.content_id == content_id)
            .count()
        ) > 0

    def upsert(
        self, content_type: str, content_id: int, vector: list, model_name: str = "all-MiniLM-L6-v2"
    ) -> Embedding:
        """
        Insert an embedding, or overwrite it if one already exists for this item
        (e.g. the summary changed and the item needs a fresh embedding).
        """
        stmt = (
            pg_insert(Embedding)
            .values(content_type=content_type, content_id=content_id, embedding=vector, model_name=model_name)
            .on_conflict_do_update(
                index_elements=["content_type", "content_id"],
                set_={"embedding": vector, "model_name": model_name},
            )
            .returning(Embedding)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def find_similar(
        self, vector: list, content_type: Optional[str] = None, limit: int = 5
    ) -> List[Tuple[Embedding, float]]:
        """
        Find the closest existing embeddings to a given vector.
        Returns (Embedding, similarity) pairs, most similar first.
        This is what Feature 7 (dedup) and Feature 2 (chatbot) will call.
        """
        query = self.db.query(
            Embedding,
            (1 - Embedding.embedding.cosine_distance(vector)).label("similarity"),
        )
        if content_type:
            query = query.filter(Embedding.content_type == content_type)
        query = query.order_by(Embedding.embedding.cosine_distance(vector)).limit(limit)
        return [(row[0], row[1]) for row in query.all()]