# app/tasks/source_submission_tasks.py
#
# "Add a source" backend (M10). Routed to the SAME "interactive" queue as
# M9's search_tasks.py — a user is waiting live for "relevance feedback"
# (per the roadmap's own Frontend bullet), so this must never queue behind
# a multi-minute pipeline run on the default queue. Django enqueues this
# task (a lightweight Celery client, see web/apps/onboarding/source_submission.py)
# and waits briefly for the result; the pipeline worker does all the real
# work — feed fetch, embedding, corpus-centroid comparison, and (if
# accepted) creating the actual Source Registry row, since only the
# pipeline process can write pipeline-owned tables.
#
# Canonicalization (dedupe by feed URL) lives HERE, not in Django, so
# there's exactly one authoritative check — Django's view only ever reads
# the result and creates its own (Django-owned) UserSourceSubscription row.

import hashlib
import logging
import re
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError

from app.celery_app import celery_app
from app.database.repositories.source_repository import SourceRepository
from app.database.session import get_db_session
from app.services.relevance_gate import evaluate_source

logger = logging.getLogger(__name__)

MIN_USER_SOURCE_SCHEDULE_HOURS = 6  # fetch-frequency floor — see run_pipeline.py's run_scraping_phases()


def _generate_source_key(feed_url: str) -> str:
    """A stable, URL-safe, unique-enough key: domain slug + a short hash of the full URL."""
    domain = urlparse(feed_url).netloc.replace("www.", "")
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_") or "feed"
    digest = hashlib.sha256(feed_url.encode("utf-8")).hexdigest()[:8]
    return f"user_{slug}_{digest}"[:50]  # Source.key is String(50)


@celery_app.task(name="app.tasks.source_submission_tasks.evaluate_and_register_source_task", queue="interactive")
def evaluate_and_register_source_task(
    feed_url: str, name: str, category: str, submitted_by_user_id: int, schedule_hours: int = 24,
) -> dict:
    with get_db_session() as db:
        repo = SourceRepository(db)

        existing = repo.get_by_feed_url(feed_url)
        if existing is not None:
            return {
                "status": "already_exists",
                "source_id": existing.id,
                "score": existing.validation_score,
                "message": f"“{existing.name}” is already in the registry — you're now subscribed.",
            }

        result = evaluate_source(feed_url, db)
        if result.decision == "rejected":
            return {"status": "rejected", "source_id": None, "score": result.score, "message": result.message}

        floor_hours = max(schedule_hours or 24, MIN_USER_SOURCE_SCHEDULE_HOURS)
        key = _generate_source_key(feed_url)

        try:
            source = repo.create_user_source(
                key=key, name=name.strip()[:200] or urlparse(feed_url).netloc, category=category,
                feed_url=feed_url, created_by=submitted_by_user_id, schedule_hours=floor_hours,
                validation_status=result.decision, validation_score=result.score,
            )
        except IntegrityError:
            # Race: someone else registered this exact feed_url in the
            # microseconds between our canonicalization check above and
            # this insert. The DB's own unique constraint on feed_url is
            # the real safety net; this just makes the race resolve to the
            # same "already_exists" outcome instead of a 500.
            db.rollback()
            existing = repo.get_by_feed_url(feed_url)
            return {
                "status": "already_exists",
                "source_id": existing.id if existing else None,
                "score": result.score,
                "message": "This feed was just added by someone else — you're now subscribed.",
            }

        return {
            "status": result.decision,
            "source_id": source.id,
            "score": result.score,
            "message": result.message,
        }
