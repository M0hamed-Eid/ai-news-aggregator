# app/celery_app.py
#
# Celery application instance for the pipeline's background job queue
# (M6 — Infrastructure Foundation). Redis is the broker + result backend.
#
# Windows dev usage (this project's dev machine):
#   Always invoke via `python -m celery`, never the bare `celery` command —
#   run_pipeline.py is a top-level script (no package, no editable install),
#   and only `python -m X` adds the current working directory to sys.path.
#   The bare `celery` console-script entry point does NOT, so it can never
#   resolve `import run_pipeline` from app/tasks/pipeline_tasks.py. Always
#   run from the repo root.
#
#   Worker: python -m celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info
#   Beat:   python -m celery -A app.celery_app:celery_app beat --loglevel=info
#
# --pool=solo works around Celery's prefork pool having known issues on
# Windows — the default prefork pool is a Linux-oriented multiprocessing
# model that doesn't behave reliably here.

import logging
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from dotenv import load_dotenv

load_dotenv()  # read .env before resolving REDIS_URL

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

celery_app = Celery(
    "ai_news_aggregator",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.health_tasks",
        "app.tasks.pipeline_tasks",
        "app.tasks.affinity_tasks",
        "app.tasks.profile_vector_tasks",
        "app.tasks.ranking_tasks",
        "app.tasks.search_tasks",
        "app.tasks.rag_tasks",
        "app.tasks.source_submission_tasks",
        "app.tasks.source_revalidation_tasks",
        "app.tasks.trend_tasks",
        "app.tasks.stt_tasks",
    ],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# Redis's broker default visibility_timeout is 3600s (1 hour): if a task is not
# acked within that window, Redis assumes the worker died and re-delivers the
# task to another consumer. run_full_pipeline_task legitimately takes ~88
# minutes (scrape + enrich + cluster + score + trends + RAG index over the whole
# corpus), so it blew past the default EVERY run and got redelivered — observed
# live as the SAME task id succeeding four times in one morning, i.e. the
# pipeline looping back-to-back around the clock instead of running every 6h.
# 6 hours matches the beat interval below, so a run can never outlive its own
# next scheduled dispatch.
celery_app.conf.broker_transport_options = {"visibility_timeout": 6 * 60 * 60}

# M9 — interactive/low-latency tasks (currently just query embedding for
# semantic search) get their OWN queue, consumed by a SEPARATE worker
# process from the default queue the 6-hourly pipeline run occupies for
# minutes at a time. Without this, a search request queued onto the same
# worker/queue as a running scrape/enrich/cluster/score pass would simply
# time out — confirmed as a real risk during M9 design review, not a
# hypothetical. task_routes here covers any sender that imports this Celery
# app; Django's own lightweight client (web/apps/news/search.py) ALSO
# passes queue="interactive" explicitly on send_task(), since it does NOT
# import this app/config (that's the whole point — it stays dependency-free).
celery_app.conf.task_routes = {
    "app.tasks.search_tasks.*": {"queue": "interactive"},
    # M14 — RAG chat answers are interactive (a user is waiting synchronously
    # on the result), same reasoning as search_tasks above — never the
    # 6-hourly default queue, which can be busy for minutes at a time.
    "app.tasks.rag_tasks.*": {"queue": "interactive"},
    # M10 — "add a source" needs live relevance feedback (a user is waiting
    # on the result synchronously), same reasoning as search_tasks above.
    "app.tasks.source_submission_tasks.*": {"queue": "interactive"},
    # M12 — STT (yt-dlp download + faster-whisper CPU transcription) is
    # compute-heavy and can take minutes per video. Its own queue keeps it
    # off the default worker so it never blocks the 6-hourly scrape/enrich
    # chain. Per docs/ROADMAP.md, this queue's worker should run on a
    # residential-IP host (`-Q stt`) — yt-dlp is more likely to get
    # rate-limited/blocked from a datacenter IP.
    "app.tasks.stt_tasks.*": {"queue": "stt"},
}

# Mirrors this project's existing cron precedent (README: "0 */6 * * *") —
# the manual run_pipeline.py CLI entry point still works for one-off runs.
celery_app.conf.beat_schedule = {
    "run-full-pipeline-every-6-hours": {
        "task": "app.tasks.pipeline_tasks.run_full_pipeline_task",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # M7 — nightly affinity aggregation + event retention prune. M9 extended
    # this task to also populate topic/entity affinity dimensions.
    "aggregate-affinities-nightly": {
        "task": "app.tasks.affinity_tasks.aggregate_affinities_task",
        "schedule": crontab(minute=0, hour=3),
    },
    # M9 — nightly profile-vector recomputation. Scheduled right after
    # affinities (3:15 vs 3:00) since both read the same user_events window;
    # not the same task because a taste VECTOR and scalar affinity WEIGHTS
    # are different outputs read by different parts of the ranker.
    "compute-profile-vectors-nightly": {
        "task": "app.tasks.profile_vector_tasks.compute_profile_vectors_task",
        "schedule": crontab(minute=15, hour=3),
    },
    # M9 — ranking runs on its OWN schedule, decoupled from the 6-hour
    # scrape/enrich/digest cadence, so /feed stays fresh in between digest
    # sends (every 3 hours vs. the pipeline's every-6-hours).
    "rank-all-users-every-3-hours": {
        "task": "app.tasks.ranking_tasks.rank_all_users_task",
        "schedule": crontab(minute=30, hour="*/3"),
    },
    # M10 — user-submitted sources drift (a feed can go off-topic, die, or
    # come back into scope); re-run the same relevance gate used at
    # submission time once a month, live, rather than trusting a one-time
    # decision forever.
    "revalidate-user-sources-monthly": {
        "task": "app.tasks.source_revalidation_tasks.revalidate_user_sources_task",
        "schedule": crontab(minute=0, hour=4, day_of_month=1),
    },
    # M11 — the only genuinely weekly, LLM-driven job in this milestone;
    # burst detection itself is LLM-free and rides the 6-hourly pipeline
    # chain instead (see run_pipeline.py's run_trend_computation_phase).
    "generate-weekly-trend-report": {
        "task": "app.tasks.trend_tasks.generate_weekly_trend_report_task",
        "schedule": crontab(minute=0, hour=6, day_of_week=1),
    },
}


@worker_process_init.connect
def _preload_embedding_model(**kwargs):
    """
    Load the sentence-transformers model once at worker startup rather than
    lazily on the first task. Without this, the FIRST call to embed_text()/
    embed_texts() on a freshly-started worker downloads+loads the model from
    Hugging Face Hub before doing any real work — measured at ~90s on a cold
    cache in this project's own Docker deployment verification, which blows
    straight through the interactive queue's 5s/20s client-side timeouts
    (web/apps/news/search.py, web/apps/onboarding/source_submission.py) even
    though the task itself succeeds moments later. This only matters for the
    interactive worker in practice (the one serving live, timeout-bound
    requests) but runs for every worker unconditionally — a few extra
    seconds at startup is trivial, and every worker calls embed_text/
    embed_texts somewhere in its own task set anyway.
    """
    try:
        from app.embeddings.embedding_service import embed_text

        embed_text("warmup")
        logger.info("Embedding model pre-loaded at worker startup.")
    except Exception:
        logger.exception("Embedding model pre-load failed — first real task will load it instead.")
