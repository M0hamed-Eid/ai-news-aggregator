# AI Compass — Recommendation Evaluation Methodology & Results

**Run date:** 2026-08-22 (UTC). **Database:** local development Postgres (`ai_news_db`, docker container `ai_news_db`, same schema/data lineage as the production database — see `docs/PRODUCTION_READINESS_AUDIT.md`). **Harness:** `app/eval/ranking_eval.py` (`RANKER_VERSION = "v1-deterministic"`), driven by the new reproducible runner `app/eval/run_offline_eval.py`. **Command:**

```bash
.venv/Scripts/python.exe -m app.eval.run_offline_eval
```

No API keys, secrets, or credentials are read or printed by this script. It performs read-only queries; it never writes to `user_rankings` or any other table. Full raw output is saved to `app/eval/offline_eval_report.json` (git-ignored — regenerate by re-running the command above).

## 1. Dataset at evaluation time

| Table | Row count |
|---|---|
| `articles` | 23,321 |
| `youtube_videos` | 244 |
| `embeddings` | 23,535 |
| `rag_chunks` | 53,761 |
| `content_clusters` | 26 |
| `content_enrichment` | 18,572 |
| `entities` | 27,753 |
| `sources` | 16 |
| `user_rankings` | 131 rows across **10 distinct users** |
| `user_affinities` | 317 |
| `user_events` | 5,458 (breakdown: impression 2,713, dwell 2,124, scroll 542, click 63, save 12, hide 4; **0** `digest_click` rows — digest opens are tracked via a separate `digest_click_tokens`/`digest_log` mechanism, not `user_events`) |
| Most recent `user_events` row | **2026-08-10** — i.e. no behavioral event of any kind has been recorded in the 12 days preceding this evaluation run |

There are only **10 users with a persisted ranking**, and only **3 of those 10** (`user_id` 1, 4, 29) have *any* click/save event on record at all (43+12+2+9+1+2+7+1 = 66 raw click/save rows across those 3 users, all dated between 2026-07-14 and 2026-08-10). This is a real, small-scale, largely-developer-generated interaction dataset (consistent with `docs/PRODUCTION_READINESS_AUDIT.md`'s "4 real users" finding and the project's live-browser-verification sessions recorded in project history) — **not** a dataset from sustained real-world usage. Every number in this report must be read with that scale in mind.

## 2. A pre-existing methodological issue found and fixed (harness only, not the recommender)

The original `build_relevance_labels()` always computed its held-out cutoff as `datetime.now(timezone.utc) - held_out_days`, i.e. relative to **whenever the evaluation script happens to run** — not relative to when the `UserRanking` row being scored was actually produced. This is a latent bug: `user_rankings` is *wholesale-replaced* on every scheduled ranking run (`UserRankingRepository.replace_for_user()` — no history is retained), so the row on disk right now for any user reflects only the **most recent** ranking pass. If that pass ran recently (which it does — `rank_all_users_task` runs every 3 hours per `app/celery_app.py`), the "held-out" window will almost always look forward past the ranking's own computation time by construction, and the intended semantics ("did the user act on this specific ranking afterward?") hold. But there is no code-level guarantee of this — and in this evaluation run, several `computed_at` timestamps for the same 10 users span from 2026-07-15 through 2026-08-22 (a fresh pass happened to run for four of them during this session), which is exactly the scenario where wall-clock-relative windowing silently stops measuring what it claims to measure.

**Fix applied** (`app/eval/ranking_eval.py`): added an optional `held_out_since: Optional[datetime]` parameter to `build_relevance_labels()`, `evaluate_user_ranking()`, and a new `anchor_to_computed_at` flag on `evaluate_all_users()`. When supplied, the cutoff is the caller's explicit timestamp (e.g. a user's own `UserRanking.computed_at`) instead of wall-clock `now`. **This is purely additive** — every existing call site that does not pass the new parameter behaves identically to before, so this is not a change to `RankingService` or to any score ever shown to a user; it only changes how the *evaluation harness* selects the window it treats as "the future" when explicitly asked to.

## 3. What the harness actually measured, and why every number is 0.0

Three passes were run (see `run_offline_eval.py` for exact code):

**Pass 1 — "naive" (harness's original, unmodified behavior, held_out_days=7):** `NDCG@10 = 0.0` and `MAP = 0.0` for **all 10 users**, with `n_relevant_held_out = 0` for all 10. This is mechanically correct given §1: the held-out window is "the last 7 days from 2026-08-22," and the most recent behavioral event in the entire database is from 2026-08-10 — there is *no event of any kind*, for *any* user, inside that window. This is an entirely expected, non-mysterious zero: the evaluation window is empty, not the ranking bad.

**Pass 2 — "retrospective correlation" (methodology fix applied, cutoff = "since 2020," i.e. capturing every click/save event on record, regardless of whether it predates the stored ranking):** of the 10 users, only 3 have any relevant events at all (`user_id=1`: 43 known relevant items; `user_id=4`: 3; `user_id=29`: 2). For **all three**, `n_relevant_within_ranked_set = 0` — meaning **zero overlap** between the specific articles/videos a user is known to have clicked or saved historically and the specific items appearing in their *currently stored* top-10/top-50 ranking. Root cause, confirmed by design (not a bug): candidate generation's dominant "recency" leg only pulls the newest 300 items at ranking time (`RECENCY_CANDIDATE_LIMIT=300`, §2.2 of the earlier audit), and the historical clicks are all 12+ days old relative to a ranking computed today — those older, previously-clicked items have long since fallen out of the recency window, and neither the similarity leg (profile-vector nearest-neighbor) nor the follows leg happened to reintroduce those specific historical items into today's top-10/top-50. **NDCG@10 and MAP are therefore undefined-in-practice (correctly computed as 0.0) not because the ranker performed badly, but because the evaluable candidate set and the historically-known-relevant set do not intersect at all at this data scale.**

**Pass 3 — baselines (chronological-recency reorder and a fixed-seed (`seed=42`) random reorder of the identical per-user candidate set):** both baselines also score `NDCG@10 = MAP = 0.0` for the same three users, for the identical reason — reordering a set with zero relevant members inside it cannot produce a nonzero score under any ordering. **The baseline comparison is therefore uninformative at this data scale, not evidence that the personalized ranker ties or loses to a naive baseline.** This must be stated plainly rather than glossed over.

## 4. Honest conclusion for the thesis

This offline harness run **proves the evaluation code itself is implemented correctly** (it consistently computes `NDCG@k`/`MAP` as textbook-defined, correctly returns 0.0 on an empty relevant-set rather than crashing or dividing by zero, and correctly distinguishes "no relevant items known" from "relevant items known but not retrieved") — but it **does not and cannot yet demonstrate ranking quality**, because:

1. The interaction dataset is minute (10 ranked users, 3 with any engagement, 66 raw relevant events total) and largely developer-generated rather than organic.
2. `user_rankings`'s wholesale-replace persistence model discards the historical ranking snapshots that would be needed to correctly pair "what a user saw" with "what they later did" at the individual-item level.
3. Candidate generation's recency bias means a meaningful held-out evaluation window needs to be *short* (hours, not weeks) relative to the ranking's own refresh cadence (3 hours) — which in turn requires near-real-time interaction logging that this project's current traffic volume does not yet produce in any usable quantity.

This is exactly the outcome `ranking_eval.py`'s own original docstring warned about ("a good number proves the harness is correct, not that one ranker beats another... until real usage provides enough held-out events") — now empirically confirmed rather than only anticipated. The thesis Evaluation chapter should present this as a genuine, disclosed limitation: the ranking algorithm's correctness is argued from its deterministic formula and the structural/idempotency properties verified elsewhere in this audit (no-LLM hot path, MMR/exploration behaving as specified, embedding-idempotency guarantees), not from an offline NDCG/MAP number, because the data does not yet exist to produce a meaningful one. Re-running `python -m app.eval.run_offline_eval` after a period of sustained real usage (ideally with `held_out_days` shortened to match the 3-hour ranking cadence) is the concrete, actionable path to a real quantitative result, and is recorded as future work.

## 5. Reproducibility record

| Field | Value |
|---|---|
| Command | `.venv/Scripts/python.exe -m app.eval.run_offline_eval` |
| Evaluation date | 2026-08-22 (UTC) |
| Harness version | `RANKER_VERSION = "v1-deterministic"` (all 131 evaluated rows) |
| k | 10 |
| Random seed (baseline shuffle only) | 42 |
| Held-out window (Pass 1) | 7 days before run time (wall clock) |
| Held-out window (Pass 2/3) | Since 2020-01-01 UTC (i.e. unbounded — all known events) |
| Code changes | `app/eval/ranking_eval.py` — additive `held_out_since`/`anchor_to_computed_at` parameters, default behavior unchanged; `app/eval/run_offline_eval.py` — new file, read-only |
| Effect on reported/served rankings | None — `RankingService` and `user_rankings` were not modified or re-run by this evaluation |
