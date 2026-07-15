# app/tasks/search_tasks.py
#
# Semantic search's query-embedding step (M9). Django has zero ML
# dependencies and never loads sentence-transformers itself — turning a
# user's free-text query into a 384-dim vector happens HERE, in the
# pipeline's Celery worker (which already has the model loaded for corpus
# embedding), and Django calls it via a lightweight Celery client
# (`.send_task(...).get(timeout=...)`, see web/apps/news/search.py) rather
# than duplicating the ML stack in a second process.
#
# Routed to its OWN "interactive" queue/worker (see app/celery_app.py's
# task_routes and the README's "Run a dedicated interactive worker"
# section) — NOT the default queue, which the 6-hourly full pipeline run
# can occupy for minutes at a time (scrape -> enrich -> cluster -> score).
# A search request queued behind that would time out. The interactive
# worker is a second `celery worker` process consuming only this queue,
# sharing the same Redis broker/backend and the same already-loaded
# sentence-transformers model (a second in-process copy, ~90MB) as the
# default-queue worker.

import logging

from app.celery_app import celery_app
from app.embeddings.embedding_service import embed_text

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.search_tasks.embed_query_task", queue="interactive")
def embed_query_task(query: str) -> list:
    """Returns a plain list of 384 floats — JSON-serializable, no numpy leaking across the Celery result backend."""
    return embed_text(query)
