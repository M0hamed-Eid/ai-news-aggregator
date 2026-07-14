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
    ],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# Mirrors this project's existing cron precedent (README: "0 */6 * * *") —
# the manual run_pipeline.py CLI entry point still works for one-off runs.
celery_app.conf.beat_schedule = {
    "run-full-pipeline-every-6-hours": {
        "task": "app.tasks.pipeline_tasks.run_full_pipeline_task",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
