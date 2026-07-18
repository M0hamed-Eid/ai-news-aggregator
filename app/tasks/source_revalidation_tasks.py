# app/tasks/source_revalidation_tasks.py
#
# Monthly re-validation (M10) — feeds drift over time (a blog can go
# off-topic, get abandoned, or come back into scope), so a one-time
# accept/reject decision made at submission time isn't enough for a
# never-curated-by-a-human source. Re-runs the SAME gate
# (app/services/relevance_gate.py) used at submission time against every
# user-submitted source, live, on a schedule.
#
# Deliberately its OWN module, not app/tasks/source_submission_tasks.py
# despite sharing the same gate — that module's tasks are routed onto the
# "interactive" queue (app/celery_app.py's task_routes wildcard-matches the
# whole module) for a user waiting on a result synchronously. This is a
# scheduled BATCH job, same profile as affinity_tasks/profile_vector_tasks,
# and belongs on the default queue instead.

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.database.repositories.source_repository import SourceRepository
from app.database.session import get_db_session
from app.services.relevance_gate import evaluate_source

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.source_revalidation_tasks.revalidate_user_sources_task")
def revalidate_user_sources_task() -> dict:
    """
    Re-evaluates every visibility='user' Source against the AI-relevance
    gate, live. A source that now rejects is deactivated (is_active=False —
    its existing articles/subscriptions are left intact, it just stops
    being scraped/surfaced going forward); one that now accepts again is
    reactivated. Global (curated) sources are never touched here — they
    were never gated in the first place.
    """
    counts = {
        "checked": 0, "accepted": 0, "accepted_low_trust": 0, "rejected": 0,
        "errors": 0, "reactivated": 0, "deactivated": 0,
    }

    with get_db_session() as db:
        repo = SourceRepository(db)
        sources = repo.get_user_sources()

        for source in sources:
            if not source.feed_url:
                continue  # shouldn't happen for a real user source, but don't let one bad row crash the whole job

            was_active = source.is_active
            try:
                result = evaluate_source(source.feed_url, db)
            except Exception:
                logger.exception(
                    "revalidate_user_sources_task: evaluate_source failed for source id=%s key=%r",
                    source.id, source.key,
                )
                counts["errors"] += 1
                continue

            source.validation_status = result.decision
            source.validation_score = result.score
            source.validated_at = datetime.now(timezone.utc)
            source.is_active = result.decision != "rejected"
            db.commit()

            counts["checked"] += 1
            counts[result.decision] += 1
            if was_active and not source.is_active:
                counts["deactivated"] += 1
            elif not was_active and source.is_active:
                counts["reactivated"] += 1

            logger.info(
                "revalidate_user_sources_task: source id=%s key=%r %s -> %s (score=%.3f)",
                source.id, source.key,
                "active" if was_active else "inactive",
                "active" if source.is_active else "inactive",
                result.score,
            )

    logger.info("revalidate_user_sources_task: done — %s", counts)
    return counts
