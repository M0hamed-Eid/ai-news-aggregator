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
    # User-submitted sources (M10)
    # =========================================================================

    def get_by_feed_url(self, feed_url: str) -> Optional[Source]:
        """Canonicalization lookup — does a user-submitted source for this exact feed URL already exist?"""
        return self.db.query(Source).filter(Source.feed_url == feed_url).first()

    def count_created_by(self, user_id: int) -> int:
        """How many sources this user has submitted — the per-user cap check reads this."""
        return self.db.query(Source).filter(Source.created_by == user_id).count()

    def get_user_sources(self) -> List[Source]:
        """Every visibility='user' source, regardless of is_active — the monthly re-validation job reads this."""
        return self.db.query(Source).filter(Source.visibility == "user").all()

    def _insert_source(
        self,
        *,
        key: str,
        name: str,
        category: str,
        adapter_type: str,
        config: dict,
        feed_url: str,
        created_by: int,
        schedule_hours: int,
        validation_status: str,
        validation_score: float,
        handler: Optional[str] = None,
    ) -> Source:
        """
        Shared row-construction helper — create_user_source (RSS) and
        create_user_youtube_source differ only in adapter_type/handler/
        config, so the actual insert/commit/log logic lives here once.
        Neither caller validates the relevance gate itself (see
        app/services/relevance_gate.py, called by the two Celery tasks in
        app/tasks/source_submission_tasks.py before either of these run).
        """
        source = Source(
            key=key,
            name=name,
            category=category,
            adapter_type=adapter_type,
            handler=handler,
            config=config,
            schedule_hours=schedule_hours,
            is_active=True,
            created_by=created_by,
            visibility="user",
            feed_url=feed_url,
            validation_status=validation_status,
            validation_score=validation_score,
            validated_at=datetime.now(timezone.utc),
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        logger.info(
            "SourceRepository: created user source id=%s key=%r feed_url=%r adapter_type=%r handler=%r "
            "(created_by=%s, validation=%s/%.3f)",
            source.id, key, feed_url, adapter_type, handler, created_by, validation_status, validation_score,
        )
        return source

    def create_user_source(
        self,
        *,
        key: str,
        name: str,
        category: str,
        feed_url: str,
        created_by: int,
        schedule_hours: int,
        validation_status: str,
        validation_score: float,
    ) -> Source:
        """
        Register a new user-submitted RSS/Atom source. One feed per row,
        config['feeds'] holding exactly one feed-definition dict so the
        existing run_scraping_phases() dispatch (which flattens every
        adapter_type='rss' row's config['feeds'] into one RssFeedScraper
        call) picks it up with zero changes.
        """
        return self._insert_source(
            key=key,
            name=name,
            category=category,
            adapter_type="rss",
            config={"feeds": [{"url": feed_url, "source": key, "label": name}]},
            feed_url=feed_url,
            created_by=created_by,
            schedule_hours=schedule_hours,
            validation_status=validation_status,
            validation_score=validation_score,
        )

    def create_user_youtube_source(
        self,
        *,
        key: str,
        name: str,
        category: str,
        channel_id: str,
        feed_url: str,
        created_by: int,
        schedule_hours: int,
        validation_status: str,
        validation_score: float,
    ) -> Source:
        """
        Register a new user-submitted YouTube channel source. Writes the
        SAME config shape HANDLER_BUILDERS["youtube"] already expects for
        the curated channel row (config["channels"]: a list of
        {"channel_id","name"} dicts) — run_scraping_phases() dispatches it
        through the existing YouTubeScraper with no new scraper code.
        feed_url is the channel's own video-list Atom feed URL (see
        app/services/youtube_channel_resolver.py) — reused purely as the
        canonicalization key exactly like an RSS source's feed_url, not a
        feed anyone reads directly.
        """
        return self._insert_source(
            key=key,
            name=name,
            category=category,
            adapter_type="api",
            handler="youtube",
            config={"channels": [{"channel_id": channel_id, "name": name}]},
            feed_url=feed_url,
            created_by=created_by,
            schedule_hours=schedule_hours,
            validation_status=validation_status,
            validation_score=validation_score,
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
