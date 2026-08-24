# app/eval/ranking_eval.py
#
# Offline evaluation harness (M9) — NDCG@10 / MAP of a stored ranking
# against held-out click/save events, plus a shadow-mode comparison (score
# an alternate ranking with the CURRENT ranker code without ever writing to
# user_rankings) — this is what lets a future ranker/weights change be
# measured before it goes live, per the roadmap's own explicit M9
# requirement ("This is what lets us later prove a new ranker beats the
# old one — critical for credibility").
#
# IMPORTANT — what a number from this module DOES and DOES NOT prove:
# at this project's current scale, held-out events are sparse and largely
# synthetic-but-realistic (same caveat M7's affinity-aggregation
# verification made explicit — see .wolf/cerebrum.md). A good NDCG/MAP
# number here proves the harness computes correctly, end to end, against
# real stored rankings and real event data — it is NOT proof that one
# ranker is objectively "better" than another; that requires real
# production-scale interaction volume. Treat every number this module
# produces as harness-correctness verification, not a ranking-quality
# claim, until real usage provides enough held-out events to trust the
# comparison (Architecture risk register: "over-tuning weights by
# intuition" — the eval harness is the guardrail, but only once there's
# enough data behind it to guard anything).

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.database.models.user_ranking import UserRanking

logger = logging.getLogger(__name__)

# Held-out "ground truth" relevance signal — save is a stronger positive
# signal than a click (matches the relative weighting already established
# in app/tasks/affinity_tasks.py's EVENT_WEIGHTS, though this is a
# separate, smaller vocabulary scoped to "did the user engage with this
# item at all", not a full affinity model).
RELEVANCE_EVENT_WEIGHTS = {"click": 1.0, "save": 2.0, "digest_click": 1.0}


def _dcg(gains: List[float]) -> float:
    return sum(gain / math.log2(idx + 2) for idx, gain in enumerate(gains))


def ndcg_at_k(ranked_keys: List[Tuple[str, int]], relevance: Dict[Tuple[str, int], float], k: int = 10) -> float:
    """Standard NDCG@k. `relevance` maps (content_type, content_id) -> a relevance score (absent/0 = unseen)."""
    gains = [relevance.get(key, 0.0) for key in ranked_keys[:k]]
    dcg = _dcg(gains)
    ideal_gains = sorted(relevance.values(), reverse=True)[:k]
    idcg = _dcg(ideal_gains)
    return (dcg / idcg) if idcg > 0 else 0.0


def average_precision(ranked_keys: List[Tuple[str, int]], relevant_keys: set) -> float:
    """MAP's per-user building block: mean of precision@i at every rank i where a relevant item appears."""
    if not relevant_keys:
        return 0.0
    hits = 0
    precisions = []
    for idx, key in enumerate(ranked_keys, start=1):
        if key in relevant_keys:
            hits += 1
            precisions.append(hits / idx)
    return (sum(precisions) / len(relevant_keys)) if precisions else 0.0


def build_relevance_labels(
    db, user_id: int, held_out_days: int = 7, held_out_since: Optional[datetime] = None
) -> Dict[Tuple[str, int], float]:
    """
    Held-out ground truth: this user's click/save/digest_click events,
    weighted. Read via the same DjangoUserEvent cross-ORM mirror
    affinity_tasks.py already uses — no new table.

    Cutoff selection (evaluation-methodology note, added during the 2026-08-22
    graduation-thesis evaluation pass — see docs/EVALUATION.md):
    the ORIGINAL implementation always derived the cutoff as
    `datetime.now(timezone.utc) - held_out_days`, i.e. relative to whenever
    the evaluation SCRIPT happens to run. That is only a valid "held-out
    future events" cutoff if the stored `UserRanking` rows being scored were
    ALSO computed close to "now" — which is not guaranteed, since
    `user_rankings` is wholesale-replaced on every ranking run (no history
    is kept). Passing an explicit `held_out_since` (e.g. the ranking's own
    `computed_at`) fixes the cutoff to the actual moment the ranking was
    produced, which is what "held-out" is supposed to mean. `held_out_days`
    is kept as the default, backward-compatible behavior when
    `held_out_since` is not supplied — no existing caller's behavior changes.
    """
    from app.database.models.django_readmodels import DjangoUserEvent

    cutoff = held_out_since if held_out_since is not None else (datetime.now(timezone.utc) - timedelta(days=held_out_days))
    events = (
        db.query(DjangoUserEvent)
        .filter(DjangoUserEvent.user_id == user_id, DjangoUserEvent.created_at >= cutoff)
        .filter(DjangoUserEvent.event_type.in_(list(RELEVANCE_EVENT_WEIGHTS.keys())))
        .filter(DjangoUserEvent.content_type.in_(["article", "youtube_video"]))
        .all()
    )
    relevance: Dict[Tuple[str, int], float] = defaultdict(float)
    for e in events:
        relevance[(e.content_type, e.content_id)] += RELEVANCE_EVENT_WEIGHTS.get(e.event_type, 0.0)
    return dict(relevance)


def evaluate_user_ranking(
    db, user_id: int, held_out_days: int = 7, k: int = 10, held_out_since: Optional[datetime] = None
) -> Optional[dict]:
    """NDCG@k + MAP for one user's CURRENTLY STORED ranking against their held-out events.

    `held_out_since`: see `build_relevance_labels` docstring. When omitted,
    behavior is unchanged from the original implementation (wall-clock
    `now - held_out_days`).
    """
    rows = (
        db.query(UserRanking)
        .filter(UserRanking.user_id == user_id)
        .order_by(UserRanking.rank.asc())
        .all()
    )
    if not rows:
        return None

    ranked_keys = [(r.content_type, r.content_id) for r in rows]
    relevance = build_relevance_labels(db, user_id, held_out_days, held_out_since=held_out_since)
    relevant_keys = {key for key, weight in relevance.items() if weight > 0}

    return {
        "user_id": user_id,
        "score_version": rows[0].score_version,
        "n_ranked": len(rows),
        "n_relevant_held_out": len(relevant_keys),
        "ndcg_at_k": round(ndcg_at_k(ranked_keys, relevance, k=k), 4),
        "map": round(average_precision(ranked_keys, relevant_keys), 4),
    }


def evaluate_all_users(
    db, held_out_days: int = 7, k: int = 10, anchor_to_computed_at: bool = False
) -> List[dict]:
    """Runs evaluate_user_ranking() for every user with a stored ranking. Skips users with none.

    `anchor_to_computed_at`: if True, each user's held-out cutoff is that
    user's own `UserRanking.computed_at` (the true "did anything happen
    AFTER this ranking was produced" cutoff) instead of wall-clock `now`.
    Default False preserves the original behavior exactly.
    """
    user_ids = [uid for (uid,) in db.query(UserRanking.user_id).distinct()]
    results = []
    for uid in user_ids:
        held_out_since = None
        if anchor_to_computed_at:
            computed_at = (
                db.query(UserRanking.computed_at)
                .filter(UserRanking.user_id == uid)
                .order_by(UserRanking.computed_at.desc())
                .limit(1)
                .scalar()
            )
            held_out_since = computed_at
        result = evaluate_user_ranking(db, uid, held_out_days=held_out_days, k=k, held_out_since=held_out_since)
        if result is not None:
            results.append(result)
    return results


def shadow_compare(db, recipient, all_items, source_categories, held_out_days: int = 7, k: int = 10) -> dict:
    """
    Shadow mode: compute a FRESH ranking via the CURRENT RankingService
    code/weights WITHOUT persisting it (no replace_for_user() call), score
    it the same way, and return it alongside the LIVE (already-persisted)
    ranking's metrics for the same user — compare "what's live" vs. "what
    the current ranker code would produce right now" before ever writing.
    """
    from app.services.ranking_service import RANKER_VERSION, RankingService

    user_id = recipient.user_id
    live = evaluate_user_ranking(db, user_id, held_out_days=held_out_days, k=k) if user_id is not None else None

    ranked_scores, item_map = RankingService(db).rank_for_user(recipient, all_items, source_categories)
    if not ranked_scores:
        return {"live": live, "shadow": None}

    shadow_keys = []
    for r in ranked_scores:
        digest = item_map.get(r.digest_id)
        if digest is None:
            continue
        content_type = "youtube_video" if digest.article_type == "youtube" else "article"
        shadow_keys.append((content_type, digest.db_id))

    relevance = build_relevance_labels(db, user_id, held_out_days) if user_id is not None else {}
    relevant_keys = {key for key, weight in relevance.items() if weight > 0}

    shadow = {
        "user_id": user_id,
        "score_version": RANKER_VERSION,
        "n_ranked": len(shadow_keys),
        "n_relevant_held_out": len(relevant_keys),
        "ndcg_at_k": round(ndcg_at_k(shadow_keys, relevance, k=k), 4),
        "map": round(average_precision(shadow_keys, relevant_keys), 4),
    }
    return {"live": live, "shadow": shadow}
