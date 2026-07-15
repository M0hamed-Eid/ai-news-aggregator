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

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()  # read .env before resolving REDIS_URL

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
    ],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

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
}
