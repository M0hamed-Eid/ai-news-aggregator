# app/database/models/content_cluster.py
#
# A cluster is just an identity/bucket — the actual grouping lives in
# ContentClusterMember rows. Rebuilt wholesale each clustering run (see
# app/tasks/pipeline_tasks.py::cluster_task / run_pipeline.py::run_clustering_phase),
# so cluster identity churns between runs — nothing external references a
# cluster id across runs (the Related view reads membership fresh per request).

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentCluster(Base):
    __tablename__ = "content_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ContentCluster id={self.id}>"
