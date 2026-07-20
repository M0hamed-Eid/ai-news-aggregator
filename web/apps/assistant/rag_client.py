"""
RAG chat client (M14) — a produce-only Celery client, same shape as
web/apps/news/search.py's `_celery_client`: never starts a worker, never
imports the actual task function (Django has no ML/LLM deps and must stay
that way), just knows the task's name and the shared broker.

Unlike search's query-embedding hop, there is no fallback here — if the
interactive worker is down or the call times out, the caller gets an
exception and should surface an honest "temporarily unavailable" response
rather than a degraded keyword-search-style substitute (there is no sane
keyword fallback for a generated, cited answer).
"""
import logging

from celery import Celery
from django.conf import settings

logger = logging.getLogger(__name__)

_ANSWER_TASK_NAME = "app.tasks.rag_tasks.rag_answer_task"
_RETRIEVE_TASK_NAME = "app.tasks.rag_tasks.rag_retrieve_task"
# Generation is slower than query embedding (search.py's 5s) — a real Groq
# 70B call plus retrieval. Kept under gunicorn's 30s default sync-worker
# timeout (web/Dockerfile) with headroom for network/queue latency.
_ANSWER_TIMEOUT_SECONDS = 25.0
# Retrieval alone (condense + embed + search + filter + assemble, no LLM
# generation) is much faster than a full answer — this only needs to beat
# retrieval latency, not generation+retrieval.
_RETRIEVE_TIMEOUT_SECONDS = 15.0

_celery_client = Celery(broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_BROKER_URL)


def ask(
    question: str,
    *,
    user_id: int,
    scope: str = "kb",
    content_type: str = None,
    content_id: int = None,
    topic_slug: str = None,
    style: str = None,
    history: list = None,
) -> dict:
    async_result = _celery_client.send_task(
        _ANSWER_TASK_NAME,
        kwargs=dict(
            question=question, user_id=user_id, scope=scope,
            content_type=content_type, content_id=content_id,
            topic_slug=topic_slug, style=style, history=history,
        ),
        queue="interactive",
    )
    return async_result.get(timeout=_ANSWER_TIMEOUT_SECONDS)


def retrieve(
    question: str,
    *,
    user_id: int,
    scope: str = "kb",
    content_type: str = None,
    content_id: int = None,
    topic_slug: str = None,
    style: str = None,
    history: list = None,
) -> dict:
    """Retrieval-only counterpart to ask() — for the streaming path (Phase D):
    returns {has_results, question, system_prompt, handle_to_citation} with
    NO generated answer yet. See app/tasks/rag_tasks.py::rag_retrieve_task."""
    async_result = _celery_client.send_task(
        _RETRIEVE_TASK_NAME,
        kwargs=dict(
            question=question, user_id=user_id, scope=scope,
            content_type=content_type, content_id=content_id,
            topic_slug=topic_slug, style=style, history=history,
        ),
        queue="interactive",
    )
    return async_result.get(timeout=_RETRIEVE_TIMEOUT_SECONDS)
