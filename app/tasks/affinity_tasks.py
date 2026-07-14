# app/tasks/affinity_tasks.py
#
# Nightly aggregation (M7): raw user_events (Django-owned, read via the
# DjangoUserEvent mirror) -> time-decayed per-user affinity weights
# (user_affinities, pipeline-owned). Also triggers Django's own retention
# prune afterward via subprocess — the pipeline never deletes rows from a
# Django-owned table itself (see django_readmodels.py's DjangoUserEvent
# docstring, and Architecture Principle 3 in docs/ROADMAP.md).
#
# Scoping (M7): only dimension="source" is computed. "topic"/"entity"
# affinities have no data to aggregate until M8 ships taxonomy/entity
# extraction — the schema already supports them, this job just has nothing
# to write for them yet.

import logging
import math
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Dict

from app.celery_app import celery_app
from app.database.models.article import Article
from app.database.models.django_readmodels import DjangoUser, DjangoUserEvent
from app.database.repositories.user_affinity_repository import UserAffinityRepository
from app.database.session import get_db_session

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_VENV_PYTHON = REPO_ROOT / "web" / ".venv" / "Scripts" / "python.exe"
WEB_MANAGE_PY = REPO_ROOT / "web" / "manage.py"

RETENTION_DAYS = 90
HALFLIFE_DAYS = 14.0
_DECAY_LAMBDA = math.log(2) / HALFLIFE_DAYS

# Heuristic per-event-type weights — a documented starting point, not a
# tuned model. M9's eval harness is the guardrail for ranking weights; this
# is one milestone earlier, just building the substrate those weights read.
EVENT_WEIGHTS = {
    "impression": 0.1,
    "click": 1.0,
    "save": 3.0,
    "hide": -2.0,
    "digest_click": 1.5,
    "scroll": 0.0,  # page-level signal, not attributable to one source
    "search": 0.0,  # no content_id to attribute to a source
}
MAX_DWELL_SECONDS = 300.0
DWELL_MAX_WEIGHT = 2.0


def _event_weight(event: DjangoUserEvent) -> float:
    if event.event_type == "dwell":
        seconds = min((event.value or 0.0) / 1000.0, MAX_DWELL_SECONDS)
        return (seconds / MAX_DWELL_SECONDS) * DWELL_MAX_WEIGHT
    return EVENT_WEIGHTS.get(event.event_type, 0.0)


def _decay(age_days: float) -> float:
    return math.exp(-_DECAY_LAMBDA * max(age_days, 0.0))


@celery_app.task(name="app.tasks.affinity_tasks.aggregate_affinities_task")
def aggregate_affinities_task() -> dict:
    now = datetime.now(dt_timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    with get_db_session() as db:
        staff_user_ids = {
            uid for (uid,) in db.query(DjangoUser.id).filter(DjangoUser.is_staff.is_(True))
        }

        events = (
            db.query(DjangoUserEvent)
            .filter(DjangoUserEvent.created_at >= cutoff)
            .filter(DjangoUserEvent.content_type.in_(["article", "youtube_video"]))
            .all()
        )

        article_ids = {e.content_id for e in events if e.content_type == "article"}
        article_sources: Dict[int, str] = {}
        if article_ids:
            for article_id, source in db.query(Article.id, Article.source).filter(Article.id.in_(article_ids)):
                article_sources[article_id] = source

        weights: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for event in events:
            if event.user_id in staff_user_ids:
                continue
            if event.content_type == "youtube_video":
                key = "youtube"
            else:
                key = article_sources.get(event.content_id)
            if key is None:
                continue

            age_days = (now - event.created_at).total_seconds() / 86400.0
            weights[event.user_id][key] += _event_weight(event) * _decay(age_days)

        repo = UserAffinityRepository(db)
        users_updated = 0
        for user_id, source_weights in weights.items():
            repo.replace_dimension_for_user(user_id, "source", dict(source_weights))
            users_updated += 1

    logger.info(
        "affinity_tasks: aggregated source affinities for %d user(s) from %d event(s)",
        users_updated, len(events),
    )

    prune_result = _prune_django_events()

    return {
        "users_updated": users_updated,
        "events_considered": len(events),
        "prune_result": prune_result,
    }


def _prune_django_events() -> str:
    """
    Retention pruning happens in DJANGO'S OWN process, via its own ORM —
    invoked as a subprocess, the same pattern already used manually
    throughout this project for cross-app commands
    (`web/.venv/Scripts/python.exe manage.py ...`). Never a direct delete
    against user_events from the pipeline side.
    """
    if not WEB_VENV_PYTHON.exists() or not WEB_MANAGE_PY.exists():
        logger.warning(
            "affinity_tasks: web venv/manage.py not found (%s / %s) — skipping event pruning this run",
            WEB_VENV_PYTHON, WEB_MANAGE_PY,
        )
        return "skipped: web venv/manage.py not found"

    # Strip env vars THIS process loaded from its own root .env before
    # spawning Django's manage.py. django-environ's Env.read_env() does NOT
    # override an already-set os.environ value, so without this the child
    # inherits the pipeline's DATABASE_URL (postgresql+psycopg2://... — not
    # a valid Django ENGINE) and REDIS_URL (Celery's broker DB 0, not
    # Django's cache DB 1) instead of reading its own web/.env. Confirmed
    # live: this exact collision broke the prune subprocess call on first
    # verification (see .wolf/buglog.json).
    child_env = os.environ.copy()
    child_env.pop("DATABASE_URL", None)
    child_env.pop("REDIS_URL", None)

    try:
        result = subprocess.run(
            [str(WEB_VENV_PYTHON), str(WEB_MANAGE_PY), "prune_old_events"],
            cwd=str(WEB_MANAGE_PY.parent),
            capture_output=True, text=True, timeout=60,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        logger.error("affinity_tasks: prune_old_events timed out")
        return "error: timed out"
    except Exception as exc:
        logger.error("affinity_tasks: prune_old_events failed to run — %s", exc, exc_info=True)
        return f"error: {exc}"

    if result.returncode != 0:
        logger.error("affinity_tasks: prune_old_events exited %d — stderr: %s", result.returncode, result.stderr)
        return f"error: exit code {result.returncode}"

    output = result.stdout.strip()
    logger.info("affinity_tasks: prune_old_events output: %s", output)
    return output
