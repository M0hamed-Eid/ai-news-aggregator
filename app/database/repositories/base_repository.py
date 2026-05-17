# app/database/repositories/base_repository.py
#
# A generic base repository that concrete repositories inherit from.
#
# Why a base repository?
# ----------------------
# get_by_id, delete, count — these are the same for every model.
# We write them once here and child classes inherit them for free.
# Each child class only implements the logic unique to its model.

import logging
from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.database.base import Base

logger = logging.getLogger(__name__)

# T is a placeholder for "any SQLAlchemy model class".
# Using TypeVar gives us type-checker support.
T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """
    Generic CRUD base class.

    Usage in a child class:
        class ArticleRepository(BaseRepository[Article]):
            def __init__(self, db: Session):
                super().__init__(db, Article)
    """

    def __init__(self, db: Session, model: Type[T]) -> None:
        self.db = db
        self.model = model

    # -------------------------------------------------------------------------
    # Read operations
    # -------------------------------------------------------------------------

    def get_by_id(self, record_id: int) -> Optional[T]:
        """Fetch a single record by its primary key. Returns None if not found."""
        return self.db.get(self.model, record_id)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Fetch a paginated list of all records, newest first."""
        return (
            self.db.query(self.model)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count(self) -> int:
        """Return the total number of rows in the table."""
        return self.db.query(self.model).count()

    # -------------------------------------------------------------------------
    # Delete operations
    # -------------------------------------------------------------------------

    def delete(self, record_id: int) -> bool:
        """
        Delete a record by ID.
        Returns True if something was deleted, False if the ID didn't exist.
        """
        record = self.get_by_id(record_id)
        if record is None:
            logger.warning(f"{self.model.__name__} id={record_id} not found for deletion")
            return False
        self.db.delete(record)
        # Note: the caller (or get_db_session context manager) commits.
        logger.info(f"Deleted {self.model.__name__} id={record_id}")
        return True

    def delete_all(self) -> int:
        """
        Delete ALL records from the table.
        Returns the number of rows deleted.
        WARNING: irreversible — only use in tests or manual admin scripts.
        """
        count = self.db.query(self.model).delete()
        logger.warning(f"Deleted ALL {count} rows from {self.model.__tablename__}")
        return count