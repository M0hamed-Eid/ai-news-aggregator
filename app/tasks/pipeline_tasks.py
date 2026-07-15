# app/tasks/pipeline_tasks.py
#
# Wraps run_pipeline.py's existing phase functions as Celery tasks. Deliberately
# imports the phase functions directly (run_scraping_phases / run_embedding_phase
# / run_digest_phase), never run_pipeline.main() — main() parses sys.argv and
# calls sys.exit(1) on error paths, neither of which is sane inside a worker
# process. The CLI entry point (`python run_pipeline.py`) is untouched and
# still works standalone for manual/one-off runs.

import logging
import os

from app.celery_app import celery_app
from run_pipeline import (
    PipelineResult,
    run_scraping_phases,
    run_embedding_phase,
    run_digest_phase,
    run_clustering_phase,
    run_scoring_phase,
)

logger = logging.getLogger(__name__)

DEFAULT_HOURS = int(os.getenv("HOURS_LOOKBACK", "144"))


@celery_app.task(name="app.tasks.pipeline_tasks.scrape_task")
def scrape_task(source_filter: str = "all", hours: int = DEFAULT_HOURS) -> dict:
    result = PipelineResult()
    run_scraping_phases(source_filter, hours, dry_run=False, result=result)
    return result.__dict__


@celery_app.task(name="app.tasks.pipeline_tasks.embed_task")
def embed_task() -> dict:
    result = PipelineResult()
    run_embedding_phase(result)
    return result.__dict__


@celery_app.task(name="app.tasks.pipeline_tasks.digest_task")
def digest_task(hours: int = DEFAULT_HOURS, skip_email: bool = False) -> dict:
    result = PipelineResult()
    run_digest_phase(hours, dry_run=False, skip_email=skip_email, result=result)
    return result.__dict__


@celery_app.task(name="app.tasks.pipeline_tasks.cluster_task")
def cluster_task() -> dict:
    result = PipelineResult()
    run_clustering_phase(result)
    return result.__dict__


@celery_app.task(name="app.tasks.pipeline_tasks.score_task")
def score_task() -> dict:
    result = PipelineResult()
    run_scoring_phase(result)
    return result.__dict__


@celery_app.task(name="app.tasks.pipeline_tasks.run_full_pipeline_task")
def run_full_pipeline_task(hours: int = DEFAULT_HOURS, skip_email: bool = False) -> dict:
    """Mirrors run_pipeline.main()'s sequence: scrape -> embed -> digest -> cluster -> score."""
    result = PipelineResult()
    run_scraping_phases("all", hours, dry_run=False, result=result)
    run_embedding_phase(result)
    run_digest_phase(hours, dry_run=False, skip_email=skip_email, result=result)
    run_clustering_phase(result)
    run_scoring_phase(result)
    return result.__dict__
