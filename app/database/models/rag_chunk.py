# app/database/models/rag_chunk.py
#
# Passage-level retrieval index for the RAG assistant (M14 — "Feature 2 (chatbot)",
# the caller the Embedding schema was explicitly reserved for; see
# app/database/repositories/embedding_repository.py::find_similar docstring).
#
# Why a SEPARATE table instead of adding chunk rows to `embeddings`?
# -----------------------------------------------------------------
# 1. The shared `embeddings` table is queried with content_type=None by BOTH
#    run_clustering_phase() and RankingService candidate-generation. Dropping
#    passage rows in there would silently pull chunks into story-clustering and
#    profile-vector candidate generation (and Django semantic search). A
#    separate table means those callers need ZERO defensive filters and stay
#    exactly as they are today.
# 2. `embeddings` is created by app/database/create_tables.py's create_all(),
#    NOT by Alembic — so an ANN index on it has no natural migration home.
#    `rag_chunks` is Alembic-owned from birth, so its HNSW index ships cleanly.
# 3. One item has ONE `embeddings` row (uq on content_type+content_id) but MANY
#    `rag_chunks` rows — different cardinality, different unique key.
#
# Same all-MiniLM-L6-v2 / 384-dim / normalized vector space as `embeddings`
# (EMBEDDING_DIM is imported, not re-declared, so the two can never drift) — a
# query vector produced by app/embeddings/embedding_service.embed_text() is
# directly comparable against these chunks with pgvector cosine distance.

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.embedding import EMBEDDING_DIM  # 384 — single source of truth

# Bump this whenever the chunking strategy OR the embedding model changes: the
# indexing phase skips any item already indexed at the CURRENT version, so a
# bump forces a wholesale re-chunk + re-embed of the corpus on the next run.
RAG_INDEX_VERSION = "v1"


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="'article' or 'youtube_video' — provenance of this passage",
    )
    content_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Points to articles.id or youtube_videos.id",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="0-based order of this passage within its document",
    )

    text: Mapped[str] = mapped_column(Text, nullable=False, comment="The passage itself, verbatim (for grounding + quoting)")

    # Article citations: character offsets into articles.content (nullable — set
    # only for article passages). Video citations: timestamp range into the
    # transcript (nullable — set only for time-anchored video passages, enabling
    # a ?t=<start> deep-link).
    char_start: Mapped[int] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int] = mapped_column(Integer, nullable=True)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=True)

    token_count: Mapped[int] = mapped_column(Integer, nullable=True, comment="Approx tokens (context-budget accounting)")

    embedding: Mapped[list] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    index_version: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="RAG_INDEX_VERSION at write time — drives incremental re-index",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "chunk_index", name="uq_rag_chunks_content_index"),
        Index("ix_rag_chunks_content", "content_type", "content_id"),
        # Approximate-nearest-neighbour index — pgvector HNSW with cosine ops.
        # Declared here so a fresh dev DB (create_all) gets it too; the Alembic
        # migration creates the same index (same name) for prod. create_all uses
        # checkfirst=True, so it won't collide when both run against one DB.
        Index(
            "ix_rag_chunks_embedding_hnsw", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        anchor = f"{self.start_seconds:.0f}s" if self.start_seconds is not None else f"@{self.char_start}"
        return f"<RagChunk {self.content_type}:{self.content_id} #{self.chunk_index} [{anchor}]>"
