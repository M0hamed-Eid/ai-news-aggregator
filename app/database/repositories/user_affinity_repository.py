# app/database/repositories/user_affinity_repository.py

import logging
from typing import Dict

from app.database.models.user_affinity import UserAffinity
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserAffinityRepository(BaseRepository[UserAffinity]):

    def __init__(self, db) -> None:
        super().__init__(db, UserAffinity)

    def replace_dimension_for_user(self, user_id: int, dimension: str, weights: Dict[str, float]) -> int:
        """
        Wholesale-replace one user's affinity rows for ONE dimension: delete
        everything they had for this dimension, insert the fresh weights.
        Recomputed from scratch each nightly run (over the full retained
        event window), not accumulated incrementally — same "replace, don't
        append" pattern as UserRankingRepository.replace_for_user().
        """
        self.db.query(UserAffinity).filter(
            UserAffinity.user_id == user_id, UserAffinity.dimension == dimension,
        ).delete()

        rows = [
            UserAffinity(user_id=user_id, dimension=dimension, key=key, weight=weight)
            for key, weight in weights.items()
        ]
        if rows:
            self.db.add_all(rows)
        self.db.commit()
        return len(rows)
