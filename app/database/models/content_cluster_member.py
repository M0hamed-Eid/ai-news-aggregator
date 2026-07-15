# app/database/models/content_cluster_member.py
#
# One item belongs to AT MOST ONE cluster at a time (UniqueConstraint on
# content_type+content_id) — clustering is wholesale-replace, not
# accumulated, matching UserRanking/UserAffinity's existing "replace, don't
# append" convention (see run_pipeline.py::run_clustering_phase).

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentClusterMember(Base):
    __tablename__ = "content_cluster_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    cluster_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("content_clusters.id"), nullable=False)
    similarity_to_centroid: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", name="uq_content_cluster_member"),
        Index("ix_content_cluster_members_cluster", "cluster_id"),
    )

    def __repr__(self) -> str:
        return f"<ContentClusterMember {self.content_type}:{self.content_id} cluster_id={self.cluster_id}>"
