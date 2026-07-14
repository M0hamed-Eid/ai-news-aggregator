# app/tasks/health_tasks.py
#
# Trivial task used to prove the Celery/Redis round-trip actually works —
# the M6 success criterion is literally "a trivial task (enqueue a log
# line) runs on a Celery worker via Redis and returns a result."

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.health_tasks.ping_task")
def ping_task(message: str = "pong") -> str:
    logger.info("[Celery] ping_task received: %s", message)
    return message
