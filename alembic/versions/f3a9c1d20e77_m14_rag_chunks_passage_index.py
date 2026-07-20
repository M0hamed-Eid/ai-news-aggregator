"""m14_rag_chunks_passage_index

Revision ID: f3a9c1d20e77
Revises: 86312c40025b
Create Date: 2026-07-19

Creates `rag_chunks`: the passage-level RAG retrieval index for the AI assistant
(M14 — "Feature 2 (chatbot)"). Deliberately a SEPARATE table from `embeddings`
(see app/database/models/rag_chunk.py for the full rationale) so that
run_clustering_phase() and RankingService candidate-generation — which query
`embeddings` with content_type=None — are left completely untouched.

Includes an HNSW approximate-nearest-neighbour index on the 384-dim pgvector
column (cosine ops). This is the first ANN index in the project; item-level
`embeddings` has none, which is fine at ~6-8k rows but would not survive the
10-50x row growth of passage-level chunking.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d20e77'
down_revision: Union[str, Sequence[str], None] = '86312c40025b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rag_chunks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('content_type', sa.String(length=20), nullable=False,
                  comment="'article' or 'youtube_video' — provenance of this passage"),
        sa.Column('content_id', sa.BigInteger(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=True),
        sa.Column('char_end', sa.Integer(), nullable=True),
        sa.Column('start_seconds', sa.Float(), nullable=True),
        sa.Column('end_seconds', sa.Float(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('index_version', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('content_type', 'content_id', 'chunk_index', name='uq_rag_chunks_content_index'),
    )
    op.create_index('ix_rag_chunks_content', 'rag_chunks', ['content_type', 'content_id'], unique=False)
    op.create_index(
        'ix_rag_chunks_embedding_hnsw', 'rag_chunks', ['embedding'], unique=False,
        postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_rag_chunks_embedding_hnsw', table_name='rag_chunks')
    op.drop_index('ix_rag_chunks_content', table_name='rag_chunks')
    op.drop_table('rag_chunks')
