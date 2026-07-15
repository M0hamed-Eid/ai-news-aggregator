# app/tasks/profile_vector_tasks.py
#
# Nightly (M9): raw user_events (Django-owned, read via DjangoUserEvent) ->
# one decayed weighted-mean embedding per user (user_profile_vectors,
# pipeline-owned) — the "taste vector" the two-stage ranker's candidate
# generation does a pgvector nearest-neighbor search against
# (app/services/ranking_service.py).
#
# Only POSITIVE, direct-engagement event types build the vector — impressions
# are too passive to represent "taste", and hide/scroll/search either have no
# meaningful vector direction or no content_id to attribute one to. This is a
# narrower event set than affinity_tasks.py's scalar affinities (which
# legitimately use hide as a negative scalar weight — subtracting a whole
# embedding vector for a "less like this" signal is a different, murkier
# operation than subtracting a scalar, so it's deliberately not attempted
# here). Reuses affinity_tasks.py's exact per-event weight/decay formula for
# consistency between "how strongly a user engages with a source" and "which
# direction their taste vector points".
#
# Users with zero qualifying weight get NO row written (not a zero/garbage
# vector) — ranking_service.py's candidate generation checks for absence and
# falls back to an onboarding-interest-derived vector for cold-start users,
# per the roadmap's own risk note ("fall back to onboarding priors").

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Dict, List

from sqlalchemy import tuple_

from app.celery_app import celery_app
from app.database.models.django_readmodels import DjangoUser, DjangoUserEvent
from app.database.models.embedding import Embedding
from app.database.repositories.user_profile_vector_repository import UserProfileVectorRepository
from app.database.session import get_db_session
from app.tasks.affinity_tasks import RETENTION_DAYS, _decay, _event_weight

logger = logging.getLogger(__name__)

PROFILE_VECTOR_EVENT_TYPES = {"click", "save", "dwell", "digest_click"}


@celery_app.task(name="app.tasks.profile_vector_tasks.compute_profile_vectors_task")
def compute_profile_vectors_task() -> dict:
    now = datetime.now(dt_timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    with get_db_session() as db:
        staff_user_ids = {
            uid for (uid,) in db.query(DjangoUser.id).filter(DjangoUser.is_staff.is_(True))
        }

        events = (
            db.query(DjangoUserEvent)
            .filter(DjangoUserEvent.created_at >= cutoff)
            .filter(DjangoUserEvent.event_type.in_(PROFILE_VECTOR_EVENT_TYPES))
            .filter(DjangoUserEvent.content_type.in_(["article", "youtube_video"]))
            .all()
        )

        content_keys = {(e.content_type, e.content_id) for e in events}
        embeddings_by_key: Dict[tuple, list] = {}
        if content_keys:
            rows = (
                db.query(Embedding.content_type, Embedding.content_id, Embedding.embedding)
                .filter(tuple_(Embedding.content_type, Embedding.content_id).in_(content_keys))
                .all()
            )
            for content_type, content_id, vector in rows:
                embeddings_by_key[(content_type, content_id)] = vector

        weighted_sums: Dict[int, List[float]] = {}
        weight_totals: Dict[int, float] = defaultdict(float)
        sample_counts: Dict[int, int] = defaultdict(int)

        for event in events:
            if event.user_id in staff_user_ids:
                continue
            vector = embeddings_by_key.get((event.content_type, event.content_id))
            if vector is None:
                continue  # item has no embedding yet (e.g. not re-embedded post-enrichment) — skip, don't crash

            age_days = (now - event.created_at).total_seconds() / 86400.0
            weight = _event_weight(event) * _decay(age_days)
            if weight <= 0:
                continue

            acc = weighted_sums.setdefault(event.user_id, [0.0] * len(vector))
            for i, v in enumerate(vector):
                acc[i] += weight * v
            weight_totals[event.user_id] += weight
            sample_counts[event.user_id] += 1

        repo = UserProfileVectorRepository(db)
        users_updated = 0
        for user_id, acc in weighted_sums.items():
            total = weight_totals[user_id]
            if total <= 0:
                continue
            mean = [x / total for x in acc]
            norm = sum(x * x for x in mean) ** 0.5
            normalized = [x / norm for x in mean] if norm > 0 else mean
            repo.upsert(user_id, normalized, sample_size=sample_counts[user_id])
            users_updated += 1

    logger.info(
        "profile_vector_tasks: computed profile vectors for %d user(s) from %d qualifying event(s)",
        users_updated, len(events),
    )
    return {"users_updated": users_updated, "events_considered": len(events)}
