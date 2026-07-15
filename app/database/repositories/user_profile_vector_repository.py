# app/database/repositories/user_profile_vector_repository.py

import logging
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models.user_profile_vector import UserProfileVector
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserProfileVectorRepository(BaseRepository[UserProfileVector]):

    def __init__(self, db) -> None:
        super().__init__(db, UserProfileVector)

    def get_for_user(self, user_id: int) -> Optional[UserProfileVector]:
        return (
            self.db.query(UserProfileVector)
            .filter(UserProfileVector.user_id == user_id)
            .first()
        )

    def upsert(
        self, user_id: int, vector: list, sample_size: int, model_name: str = "all-MiniLM-L6-v2",
    ) -> UserProfileVector:
        """
        Insert or overwrite this user's profile vector wholesale — recomputed
        from scratch each run over the full retained event window, not
        accumulated incrementally (same "replace, don't append" pattern as
        UserAffinityRepository/UserRankingRepository).
        """
        stmt = (
            pg_insert(UserProfileVector)
            .values(
                user_id=user_id, vector=vector, sample_size=sample_size, model_name=model_name,
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"vector": vector, "sample_size": sample_size, "model_name": model_name},
            )
            .returning(UserProfileVector)
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()
