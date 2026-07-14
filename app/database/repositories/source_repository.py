# app/database/repositories/source_repository.py
#
# Handles all database operations for the Source Registry (app/database/models/source.py).
#
# This repository is read-mostly from the pipeline's point of view: run_pipeline.py
# queries get_active()/get_active_by_keys() to decide what to scrape, builds the
# right scraper from each row's .config via HANDLER_BUILDERS, and calls mark_run()
# after each attempt to record when the source last ran/succeeded.

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.database.models.source import Source
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SourceRepository(BaseRepository[Source]):

    def __init__(self, db: Session) -> None:
        super().__init__(db, Source)

    # =========================================================================
    # Query helpers
    # =========================================================================

    def get_active(self) -> List[Source]:
        """Return every active source, in no particular guaranteed order."""
        return (
            self.db.query(Source)
            .filter(Source.is_active.is_(True))
            .all()
        )

    def get_by_key(self, key: str) -> Optional[Source]:
        """Fetch a single source by its stable registry key (e.g. 'arxiv')."""
        return (
            self.db.query(Source)
            .filter(Source.key == key)
            .first()
        )

    def get_active_by_keys(self, keys: List[str]) -> List[Source]:
        """Return active sources whose key is in the given list (used for --source filtering)."""
        if not keys:
            return []
        return (
            self.db.query(Source)
            .filter(Source.is_active.is_(True))
            .filter(Source.key.in_(keys))
            .all()
        )

    # =========================================================================
    # Run tracking
    # =========================================================================

    def mark_run(self, source_id: int, success: bool) -> None:
        """
        Record that a source was attempted. Always sets last_run_at=now();
        also sets last_success_at=now() when the run succeeded. Commits.
        """
        source = self.get_by_id(source_id)
        if source is None:
            logger.warning(f"mark_run: Source id={source_id} not found")
            return

        now = datetime.now(timezone.utc)
        source.last_run_at = now
        if success:
            source.last_success_at = now

        self.db.commit()
        logger.info(f"Source id={source_id} key={source.key!r} mark_run(success={success})")
