"""
Semantic search (M9). Turns a free-text query into a vector via a
lightweight Celery client — no ML dependencies in this process; the actual
sentence-transformers inference happens in the pipeline's dedicated
"interactive" Celery worker (see app/tasks/search_tasks.py's module
docstring for the full architecture rationale). This module only sends the
task, waits briefly for the result, then runs the cosine-distance query
directly against the shared Postgres via apps.catalog.models.Embedding.

Graceful degradation: if the round-trip times out or errors (e.g. the
interactive worker isn't running), falls back to the existing `icontains`
keyword search rather than a 500 — callers get back whether semantic search
actually ran, so the template can show an honest "showing keyword results
instead" notice rather than silently degrading.
"""
import logging

from celery import Celery
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from pgvector.django import CosineDistance

from apps.catalog.models import Article, Embedding, YoutubeVideo

logger = logging.getLogger(__name__)

_EMBED_TASK_NAME = "app.tasks.search_tasks.embed_query_task"
_EMBED_TIMEOUT_SECONDS = 5.0
_CACHE_TTL_SECONDS = 3600
_CACHE_KEY_PREFIX = "search:query_embedding:"

# A "produce only" Celery client — never starts a worker, never needs to
# import the actual task function, just knows its name + the shared broker.
_celery_client = Celery(broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_BROKER_URL)


def _embed_query(query: str):
    cache_key = _CACHE_KEY_PREFIX + query.strip().lower()

    # Found live on Render (2026-08-09): the cache read was OUTSIDE this
    # try/except, so an unreachable cache backend (REDIS_URL unset — see
    # apps.behavior.ratelimit's identical "Redis unavailable, failing
    # open" precedent) raised before ever reaching the "worker unavailable"
    # fallback below, 500ing the whole search request instead of degrading
    # to keyword search as designed. Same discipline as ratelimit.py: any
    # cache-layer failure fails open (treated as a cache miss), not a hard
    # error — this function's whole contract is "return None on ANY
    # reason semantic search can't run right now."
    try:
        cached = cache.get(cache_key)
    except Exception as exc:
        logger.warning("semantic search: cache read failed — %s", exc)
        cached = None
    if cached is not None:
        return cached

    try:
        async_result = _celery_client.send_task(_EMBED_TASK_NAME, args=[query], queue="interactive")
        vector = async_result.get(timeout=_EMBED_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("semantic search: query embedding failed/timed out — %s", exc)
        return None

    try:
        cache.set(cache_key, vector, _CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("semantic search: cache write failed — %s", exc)
    return vector


def semantic_search(query: str, limit: int = 20):
    """Returns (results: list[Article | YoutubeVideo], used_semantic: bool)."""
    query = (query or "").strip()
    if not query:
        return [], True

    vector = _embed_query(query)
    if vector is not None:
        nearest = (
            Embedding.objects.annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")[: limit * 2]  # over-fetch a little — some ids may resolve to nothing (rare, e.g. deleted content)
        )
        results = []
        for emb in nearest:
            model = Article if emb.content_type == "article" else YoutubeVideo
            obj = model.objects.filter(pk=emb.content_id).first()
            if obj is not None:
                results.append(obj)
            if len(results) >= limit:
                break
        return results, True

    logger.info("semantic search unavailable for query=%r — falling back to keyword search", query)
    articles = Article.objects.filter(
        Q(title__icontains=query) | Q(summary__icontains=query) | Q(author__icontains=query)
    )
    videos = YoutubeVideo.objects.filter(
        Q(title__icontains=query) | Q(summary__icontains=query) | Q(channel_name__icontains=query)
    )
    combined = list(articles) + list(videos)
    combined.sort(key=lambda item: item.published_at, reverse=True)
    return combined[:limit], False
