# app/scripts/run_scheduled_job.py
#
# Render fallback deployment path ONLY (see docs/DEPLOYMENT.md) - lets
# GitHub Actions (.github/workflows/pipeline.yml) trigger the 5 non-"full
# pipeline" beat_schedule jobs without needing a live Celery worker/beat
# process. Not used on the primary Oracle Cloud path, where Celery beat
# runs these unmodified on its own schedule (app/celery_app.py).
#
# Calls each task's underlying function DIRECTLY (not via .delay()/
# apply_async()) - a function decorated with @celery_app.task remains a
# plain, synchronously-callable Python function when invoked this way, so
# this is zero new business logic, purely scheduling plumbing. The 6th beat
# job (the full scrape->embed->digest->cluster->score->trends chain) is
# NOT here - run_pipeline.py's own CLI entry point already does that
# unchanged (`python run_pipeline.py`), which is what pipeline.yml calls
# directly instead of going through this dispatcher.

import argparse
import logging

from app.tasks.affinity_tasks import aggregate_affinities_task
from app.tasks.profile_vector_tasks import compute_profile_vectors_task
from app.tasks.ranking_tasks import rank_all_users_task
from app.tasks.source_revalidation_tasks import revalidate_user_sources_task
from app.tasks.trend_tasks import generate_weekly_trend_report_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JOBS = {
    "affinity": aggregate_affinities_task,
    "profile_vectors": compute_profile_vectors_task,
    "ranking": rank_all_users_task,
    "source_revalidation": revalidate_user_sources_task,
    "trend_report": generate_weekly_trend_report_task,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, choices=sorted(JOBS.keys()))
    args = parser.parse_args()

    logger.info("Running scheduled job: %s", args.job)
    result = JOBS[args.job]()
    logger.info("Job %s completed: %s", args.job, result)


if __name__ == "__main__":
    main()
