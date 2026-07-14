# app/database/repositories/digest_log_repository.py

import logging

from app.database.models.digest_log import DigestLog
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class DigestLogRepository(BaseRepository[DigestLog]):

    def __init__(self, db) -> None:
        super().__init__(db, DigestLog)

    def log_sent(self, user_id: int) -> None:
        """Record that a digest email was successfully sent to this user."""
        self.db.add(DigestLog(user_id=user_id))
        self.db.commit()
        logger.info(f"DigestLog: recorded send for user_id={user_id}")

    def count_for_user(self, user_id: int) -> int:
        return self.db.query(DigestLog).filter(DigestLog.user_id == user_id).count()
