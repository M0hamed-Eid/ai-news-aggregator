# app/database/repositories/content_chunk_repository.py

import logging
from typing import List, Tuple

from app.database.models.content_chunk import ContentChunk
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ContentChunkRepository(BaseRepository[ContentChunk]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentChunk)

    def replace_for_content(
        self, content_type: str, content_id: int,
        chunks: List[Tuple[float, float, str, str]], summary_version: str,
    ) -> int:
        """
        Wholesale-replace one item's chunks (delete-then-insert, same
        per-item convention as ContentEntityRepository.replace_for_content —
        NOT a global replace like ContentClusterRepository.replace_all,
        since chunking is computed independently per video, not corpus-wide
        in one pass). `chunks` is an ordered list of
        (start_seconds, end_seconds, chapter_title, chunk_summary) tuples.
        """
        self.db.query(ContentChunk).filter(
            ContentChunk.content_type == content_type, ContentChunk.content_id == content_id,
        ).delete()

        for index, (start, end, chapter_title, chunk_summary) in enumerate(chunks):
            self.db.add(ContentChunk(
                content_type=content_type, content_id=content_id, chunk_index=index,
                start_seconds=start, end_seconds=end,
                chapter_title=chapter_title, chunk_summary=chunk_summary,
                summary_version=summary_version,
            ))

        self.db.commit()
        return len(chunks)

    def get_for_content(self, content_type: str, content_id: int) -> List[ContentChunk]:
        return (
            self.db.query(ContentChunk)
            .filter(ContentChunk.content_type == content_type, ContentChunk.content_id == content_id)
            .order_by(ContentChunk.chunk_index.asc())
            .all()
        )

    def has_chunks(self, content_type: str, content_id: int) -> bool:
        return (
            self.db.query(ContentChunk.id)
            .filter(ContentChunk.content_type == content_type, ContentChunk.content_id == content_id)
            .first()
            is not None
        )
