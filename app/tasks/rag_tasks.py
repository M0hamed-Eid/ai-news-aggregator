# app/tasks/rag_tasks.py
#
# M14 — interactive RAG chat task, on the SAME "interactive" queue as
# search_tasks.py's embed_query_task (low-latency, separate worker from the
# 6-hourly batch pipeline queue — see app/celery_app.py's own rationale).
# Kept in its own file rather than added to search_tasks.py (query-embedding
# only) or pipeline_tasks.py (wraps run_pipeline.py's batch PHASE functions
# specifically) — this is neither: an on-demand, per-request answer, not a
# phase over the whole corpus.
#
# Unlike embed_query_task (Django has no ML deps, so even turning a query into
# a vector must cross to this worker), THIS task does retrieval AND
# generation in one call — see app/services/rag_service.py's own docstring
# for why that single hop is enough here.

import logging

from app.celery_app import celery_app
from app.database import get_db_session
from app.services.rag_service import answer_question, build_retrieval_payload

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.rag_tasks.rag_answer_task")
def rag_answer_task(
    question: str,
    user_id: int = None,
    scope: str = "kb",
    content_type: str = None,
    content_id: int = None,
    topic_slug: str = None,
    style: str = None,
    history: list = None,
) -> dict:
    with get_db_session() as db:
        return answer_question(
            db, question,
            user_id=user_id, scope=scope, content_type=content_type,
            content_id=content_id, topic_slug=topic_slug, style=style,
            history=history,
        )


@celery_app.task(name="app.tasks.rag_tasks.rag_retrieve_task")
def rag_retrieve_task(
    question: str,
    user_id: int = None,
    scope: str = "kb",
    content_type: str = None,
    content_id: int = None,
    topic_slug: str = None,
    style: str = None,
    history: list = None,
) -> dict:
    """
    Phase D — retrieval-only counterpart to rag_answer_task, for the
    streaming path (web/apps/assistant/views.py::AssistantStreamView).
    Condenses + retrieves + assembles a ready system_prompt, but stops
    BEFORE generation, so Django's streaming view can open its OWN Groq
    stream (needed for token-by-token delivery — Celery's request/response
    boundary can't stream) without importing anything from app/ beyond this
    one JSON-serializable payload.
    """
    with get_db_session() as db:
        return build_retrieval_payload(
            db, question,
            user_id=user_id, scope=scope, content_type=content_type,
            content_id=content_id, topic_slug=topic_slug, style=style,
            history=history,
        )
