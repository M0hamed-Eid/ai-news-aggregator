# app/tasks/ranking_tasks.py
#
# Scheduled ranking refresh (M9) — decoupled from digest send cadence
# (Architecture Principle 6 / the roadmap's own explicit M9 requirement:
# "Move ranking to its own scheduled job... so /feed stays fresh"). Fetches
# the shared content pool ONCE (Principle 1: ingest/fetch once, personalize
# at read/serve time), then computes and persists one ranking per active
# recipient via RankingService.
#
# DigestService (app/services/digest_service.py) no longer ranks
# synchronously at send time — it just reads whatever this task last wrote
# to user_rankings, falling back to an on-demand RankingService call only
# for a recipient with no ranking yet at all (cold start / this task hasn't
# fired since they signed up).

import logging
from typing import List, Union

from app.celery_app import celery_app
from app.database.models.article import Article
from app.database.models.youtube_video import YoutubeVideo
from app.database.repositories.article_repository import ArticleRepository
from app.database.repositories.user_ranking_repository import UserRankingRepository
from app.database.repositories.youtube_repository import YoutubeRepository
from app.database.session import get_db_session
from app.services.ranking_service import RANKER_VERSION, RankingService
from app.services.recipients import get_active_recipients, get_source_categories

logger = logging.getLogger(__name__)

DEFAULT_HOURS_WINDOW = 336  # 14 days — wider than the digest's own window so
# candidate generation's recency leg has real breadth to select/diversify from,
# not just whatever the last few hours happened to produce.
DEFAULT_ITEM_LIMIT = 1000


@celery_app.task(name="app.tasks.ranking_tasks.rank_all_users_task")
def rank_all_users_task(hours: int = DEFAULT_HOURS_WINDOW) -> dict:
    users_ranked = 0
    total_items_ranked = 0
    errors: List[str] = []

    with get_db_session() as db:
        all_items: List[Union[Article, YoutubeVideo]] = (
            ArticleRepository(db).get_recent(hours=hours, limit=DEFAULT_ITEM_LIMIT)
            + YoutubeRepository(db).get_recent(hours=hours, limit=DEFAULT_ITEM_LIMIT)
        )
        if not all_items:
            logger.warning("rank_all_users_task: no content in the last %d hours", hours)
            return {"users_ranked": 0, "total_items_ranked": 0, "errors": []}

        recipients = get_active_recipients(db)
        source_categories = get_source_categories(db)
        if not recipients:
            logger.warning("rank_all_users_task: no recipients found")
            return {"users_ranked": 0, "total_items_ranked": 0, "errors": []}

        ranker = RankingService(db)
        ranking_repo = UserRankingRepository(db)

        for recipient in recipients:
            if recipient.user_id is None:
                continue  # nothing to persist a ranking against (zero-active-users fallback)
            try:
                ranked_scores, item_map = ranker.rank_for_user(recipient, all_items, source_categories)
                if not ranked_scores:
                    logger.info("rank_all_users_task: no ranked items for user_id=%s", recipient.user_id)
                    continue
                ranking_repo.replace_for_user(recipient.user_id, ranked_scores, item_map, score_version=RANKER_VERSION)
                users_ranked += 1
                total_items_ranked += len(ranked_scores)
            except Exception as exc:
                msg = f"rank_all_users_task: ranking failed for user_id={recipient.user_id} — {exc}"
                logger.error(msg, exc_info=True)
                errors.append(msg)

    logger.info(
        "rank_all_users_task: ranked %d item(s) across %d user(s), %d error(s)",
        total_items_ranked, users_ranked, len(errors),
    )
    return {"users_ranked": users_ranked, "total_items_ranked": total_items_ranked, "errors": errors}
