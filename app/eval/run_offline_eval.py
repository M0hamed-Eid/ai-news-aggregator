# app/eval/run_offline_eval.py
#
# Reproducible offline-evaluation runner for the graduation-thesis
# Evaluation chapter (added 2026-08-22). Wraps app/eval/ranking_eval.py
# with three passes over the REAL local database, and prints/saves a
# single JSON report:
#
#   1. "naive"        — the eval harness's original behavior verbatim
#                        (held-out window = wall-clock now - held_out_days).
#   2. "retrospective" — a corrected-cutoff pass (see ranking_eval.py's
#                        `held_out_since` docstring) that instead asks
#                        "does this user's CURRENTLY STORED ranking order
#                        align with their full known click/save history,
#                        regardless of when it happened" — because
#                        `user_rankings` is wholesale-replaced on every run
#                        (no history kept), the row being scored was almost
#                        always computed AFTER the events used to label it.
#                        This is a RETROSPECTIVE CORRELATION check, not a
#                        forward-looking held-out prediction — see
#                        docs/EVALUATION.md for the full methodology
#                        discussion and why this distinction matters.
#   3. "baselines"     — for the same users/candidate sets used in pass 2,
#                        two baseline re-orderings of the IDENTICAL item
#                        set (chronological-recency, and a fixed-seed
#                        random shuffle), scored against the same
#                        relevance labels — isolates whether the
#                        personalized ORDER beats a naive order of the
#                        same already-selected items.
#
# Run with:  .venv/Scripts/python.exe -m app.eval.run_offline_eval
#
# No writes to the database. No changes to RankingService. No API keys or
# secrets are read or printed.

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database.session import get_db_session  # noqa: E402
from app.database.models.user_ranking import UserRanking  # noqa: E402
from app.database.models.article import Article  # noqa: E402
from app.database.models.youtube_video import YoutubeVideo  # noqa: E402
from app.eval.ranking_eval import (  # noqa: E402
    average_precision,
    build_relevance_labels,
    evaluate_all_users,
    ndcg_at_k,
)

RANDOM_SEED = 42
K = 10
RETROSPECTIVE_SINCE = datetime(2020, 1, 1, tzinfo=timezone.utc)  # "since the beginning of time" -> captures ALL known events


def _published_at_lookup(db, ranked_keys):
    article_ids = [cid for (ctype, cid) in ranked_keys if ctype == "article"]
    video_ids = [cid for (ctype, cid) in ranked_keys if ctype == "youtube_video"]
    lookup = {}
    if article_ids:
        for aid, pub in db.query(Article.id, Article.published_at).filter(Article.id.in_(article_ids)).all():
            lookup[("article", aid)] = pub
    if video_ids:
        for vid, pub in db.query(YoutubeVideo.id, YoutubeVideo.published_at).filter(YoutubeVideo.id.in_(video_ids)).all():
            lookup[("youtube_video", vid)] = pub
    return lookup


def _score(ranked_keys, relevance, relevant_keys, k=K):
    return {
        "ndcg_at_k": round(ndcg_at_k(ranked_keys, relevance, k=k), 4),
        "map": round(average_precision(ranked_keys, relevant_keys), 4),
    }


def main():
    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "k": K,
        "random_seed": RANDOM_SEED,
        "score_version_evaluated": None,
        "naive_pass": None,
        "retrospective_pass": [],
        "dataset": {},
    }

    with get_db_session() as db:
        # --- dataset description (for reproducibility/methodology reporting) ---
        total_rankings = db.query(UserRanking).count()
        ranked_user_ids = sorted({uid for (uid,) in db.query(UserRanking.user_id).distinct().all()})
        report["dataset"]["user_rankings_rows"] = total_rankings
        report["dataset"]["distinct_ranked_users"] = len(ranked_user_ids)
        report["dataset"]["ranked_user_ids"] = ranked_user_ids

        # --- Pass 1: naive, exactly as originally implemented ---
        naive_results = evaluate_all_users(db, held_out_days=7, k=K, anchor_to_computed_at=False)
        report["naive_pass"] = naive_results
        if naive_results:
            report["score_version_evaluated"] = naive_results[0]["score_version"]

        # --- Pass 2 + 3: retrospective correlation + baselines ---
        for uid in ranked_user_ids:
            rows = (
                db.query(UserRanking)
                .filter(UserRanking.user_id == uid)
                .order_by(UserRanking.rank.asc())
                .all()
            )
            if not rows:
                continue
            personalized_keys = [(r.content_type, r.content_id) for r in rows]
            computed_at = rows[0].computed_at

            relevance = build_relevance_labels(db, uid, held_out_since=RETROSPECTIVE_SINCE)
            relevant_keys = {key for key, w in relevance.items() if w > 0}

            entry = {
                "user_id": uid,
                "score_version": rows[0].score_version,
                "computed_at": computed_at.isoformat() if computed_at else None,
                "n_ranked": len(personalized_keys),
                "n_relevant_known_ever": len(relevant_keys),
                "n_relevant_within_ranked_set": len(relevant_keys & set(personalized_keys)),
            }

            if relevant_keys:
                entry["personalized"] = _score(personalized_keys, relevance, relevant_keys)

                pub_lookup = _published_at_lookup(db, personalized_keys)
                chrono_keys = sorted(
                    personalized_keys,
                    key=lambda key: pub_lookup.get(key) or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                entry["baseline_chronological"] = _score(chrono_keys, relevance, relevant_keys)

                rng = random.Random(RANDOM_SEED)
                random_keys = list(personalized_keys)
                rng.shuffle(random_keys)
                entry["baseline_random"] = _score(random_keys, relevance, relevant_keys)
            else:
                entry["personalized"] = None
                entry["baseline_chronological"] = None
                entry["baseline_random"] = None

            report["retrospective_pass"].append(entry)

    out_path = Path(__file__).resolve().parent / "offline_eval_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report, indent=2, default=str))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
