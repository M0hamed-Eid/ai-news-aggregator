"""
"Add a source" backend (M10). A lightweight Celery client — same pattern as
apps.news.search — enqueues the actual relevance-gating work onto the
pipeline's "interactive" queue (app/tasks/source_submission_tasks.py) and
waits briefly for the result. Django never fetches feeds or embeds text
itself; it only reads the decision back and creates its own (Django-owned)
UserSourceSubscription row.

The per-user submission CAP is checked here, locally, BEFORE enqueueing —
no need to burden the pipeline task with an entitlements/plan concept that's
a Django-side domain to begin with, and it saves a queue round-trip for the
common "you're already at your limit" case.
"""
import logging

from celery import Celery
from django.conf import settings

from apps.accounts.entitlements import user_can
from apps.catalog.models import Source
from apps.onboarding.models import UserSourceSubscription

logger = logging.getLogger(__name__)

_SUBMIT_TASK_NAME = "app.tasks.source_submission_tasks.evaluate_and_register_source_task"
_SUBMIT_TIMEOUT_SECONDS = 20.0  # feed fetch + embedding ~10 short items — generous but bounded

FREE_CUSTOM_SOURCE_LIMIT = 3

_celery_client = Celery(broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_BROKER_URL)


def submit_source(user, feed_url: str, name: str, category: str) -> dict:
    """
    Returns a dict with at least {"ok": bool, "message": str}. On success
    also auto-subscribes the submitter to the resulting source.
    """
    feed_url = (feed_url or "").strip()
    name = (name or "").strip()
    if not feed_url or not name:
        return {"ok": False, "message": "Both a feed URL and a name are required."}

    if not user_can(user, "unlimited_custom_sources"):
        existing_count = Source.objects.filter(created_by=user.id).count()
        if existing_count >= FREE_CUSTOM_SOURCE_LIMIT:
            return {
                "ok": False,
                "message": f"Free accounts can add up to {FREE_CUSTOM_SOURCE_LIMIT} custom sources — upgrade to Pro for unlimited.",
            }

    try:
        async_result = _celery_client.send_task(
            _SUBMIT_TASK_NAME,
            kwargs={
                "feed_url": feed_url, "name": name, "category": category,
                "submitted_by_user_id": user.id,
            },
            queue="interactive",
        )
        result = async_result.get(timeout=_SUBMIT_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("submit_source: relevance gate call failed/timed out for %r — %s", feed_url, exc)
        return {"ok": False, "message": "Couldn't validate that feed right now — please try again in a moment."}

    if result.get("source_id") is not None:
        UserSourceSubscription.objects.get_or_create(profile=user.profile, source_id=result["source_id"])

    ok = result["status"] in ("accepted", "accepted_low_trust", "already_exists")
    return {"ok": ok, "status": result["status"], "message": result["message"], "score": result.get("score")}
