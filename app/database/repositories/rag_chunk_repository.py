# app/database/repositories/rag_chunk_repository.py
#
# Data access for the passage-level RAG index (M14). Mirrors the conventions of
# EmbeddingRepository (pgvector cosine similarity) and ContentChunkRepository
# (per-item wholesale replace_for_content, commits itself).

import logging
from typing import List, Optional, Sequence, Tuple

from app.database.models.rag_chunk import RagChunk
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class RagChunkRepository(BaseRepository[RagChunk]):

    def __init__(self, db) -> None:
        super().__init__(db, RagChunk)

    def is_indexed_at(self, content_type: str, content_id: int, index_version: str) -> bool:
        """True if this item already has passages at the given index version."""
        return (
            self.db.query(RagChunk.id)
            .filter(
                RagChunk.content_type == content_type,
                RagChunk.content_id == content_id,
                RagChunk.index_version == index_version,
            )
            .first()
            is not None
        )

    def replace_for_content(
        self,
        content_type: str,
        content_id: int,
        passages: Sequence,           # Sequence[app.rag.chunker.Passage]
        embeddings: Sequence[list],   # aligned 1:1 with passages
        index_version: str,
    ) -> int:
        """
        Wholesale-replace one item's passages (delete-then-insert, per-item —
        same convention as ContentChunkRepository.replace_for_content). Commits
        itself so a long backfill persists incrementally per item rather than in
        one all-or-nothing transaction.
        """
        if len(passages) != len(embeddings):
            raise ValueError(
                f"passages/embeddings length mismatch: {len(passages)} vs {len(embeddings)}"
            )

        self.db.query(RagChunk).filter(
            RagChunk.content_type == content_type,
            RagChunk.content_id == content_id,
        ).delete()

        for idx, (p, vec) in enumerate(zip(passages, embeddings)):
            self.db.add(RagChunk(
                content_type=content_type,
                content_id=content_id,
                chunk_index=idx,
                text=p.text,
                char_start=p.char_start,
                char_end=p.char_end,
                start_seconds=p.start_seconds,
                end_seconds=p.end_seconds,
                token_count=p.token_count,
                embedding=vec,
                index_version=index_version,
            ))

        self.db.commit()
        return len(passages)

    def find_similar(
        self,
        vector: list,
        content_type: Optional[str] = None,
        content_id: Optional[int] = None,
        limit: int = 8,
    ) -> List[Tuple[RagChunk, float]]:
        """
        Nearest passages to a query vector via pgvector cosine distance.
        Optional (content_type, content_id) scope the search to one document
        (the "this article / this video" scope). Returns (chunk, similarity),
        most similar first. This is the retriever's core call in Phase B.
        """
        query = self.db.query(
            RagChunk,
            (1 - RagChunk.embedding.cosine_distance(vector)).label("similarity"),
        )
        if content_type:
            query = query.filter(RagChunk.content_type == content_type)
        if content_id is not None:
            query = query.filter(RagChunk.content_id == content_id)
        query = query.order_by(RagChunk.embedding.cosine_distance(vector)).limit(limit)
        return [(row[0], row[1]) for row in query.all()]

    def get_for_content(self, content_type: str, content_id: int) -> List[RagChunk]:
        return (
            self.db.query(RagChunk)
            .filter(RagChunk.content_type == content_type, RagChunk.content_id == content_id)
            .order_by(RagChunk.chunk_index.asc())
            .all()
        )
