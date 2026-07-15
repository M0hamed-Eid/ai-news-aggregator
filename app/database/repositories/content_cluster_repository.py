# app/database/repositories/content_cluster_repository.py
#
# Clustering is a global, non-user computation, wholesale-replaced every run
# (Principle 1: ingest once, never per-user; matches UserRanking/UserAffinity's
# existing "replace, don't accumulate" convention — see run_pipeline.py's
# run_clustering_phase for the Union-Find-over-pgvector-neighbors algorithm
# that produces the `clusters` argument below).

import logging
from typing import List, Tuple

from app.database.models.content_cluster import ContentCluster
from app.database.models.content_cluster_member import ContentClusterMember
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ContentClusterRepository(BaseRepository[ContentCluster]):

    def __init__(self, db) -> None:
        super().__init__(db, ContentCluster)

    def replace_all(self, clusters: List[List[Tuple[str, int]]]) -> int:
        """
        Wholesale-replace the entire cluster set. `clusters` is a list of
        connected components, each a list of (content_type, content_id)
        pairs. Components with fewer than 2 members are skipped — a
        "cluster of one" has no related content to surface, same as having
        no cluster at all, so there's no point storing it.
        """
        self.db.query(ContentClusterMember).delete()
        self.db.query(ContentCluster).delete()

        total_members = 0
        for members in clusters:
            if len(members) < 2:
                continue
            cluster = ContentCluster()
            self.db.add(cluster)
            self.db.flush()  # populate cluster.id without committing yet
            for content_type, content_id in members:
                self.db.add(ContentClusterMember(
                    content_type=content_type, content_id=content_id, cluster_id=cluster.id,
                ))
            total_members += len(members)

        self.db.commit()
        logger.info(
            "ContentCluster: rebuilt %d cluster(s) covering %d item(s)",
            sum(1 for m in clusters if len(m) >= 2), total_members,
        )
        return total_members

    def get_cluster_members(self, content_type: str, content_id: int) -> List[Tuple[str, int]]:
        """Other items in the SAME cluster as (content_type, content_id), or [] if unclustered."""
        member = (
            self.db.query(ContentClusterMember)
            .filter(ContentClusterMember.content_type == content_type, ContentClusterMember.content_id == content_id)
            .first()
        )
        if member is None:
            return []
        others = (
            self.db.query(ContentClusterMember)
            .filter(
                ContentClusterMember.cluster_id == member.cluster_id,
                ~((ContentClusterMember.content_type == content_type) & (ContentClusterMember.content_id == content_id)),
            )
            .all()
        )
        return [(m.content_type, m.content_id) for m in others]
