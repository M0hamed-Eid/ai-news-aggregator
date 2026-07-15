# app/database/repositories/user_ranking_repository.py
#
# Deliberately does NOT import app.ranking.types — that module (and
# app.agents/app.services generally) imports FROM app.database, so importing
# it here would create a circular import. `ranked_scores`/`item_map` are
# app.ranking.types.RankedArticle / DigestItem instances at runtime (see
# app/services/ranking_service.py, the only writer), but this file only
# touches their `.digest_id`/`.rank`/`.relevance_score`/`.reasoning`/
# `.features`/`.article_type`/`.db_id` attributes — duck-typed, no import needed.

import logging
from typing import List, Optional

from app.database.models.user_ranking import UserRanking
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class UserRankingRepository(BaseRepository[UserRanking]):

    def __init__(self, db) -> None:
        super().__init__(db, UserRanking)

    def get_for_user(self, user_id: int, limit: Optional[int] = None) -> List[UserRanking]:
        """
        Read back the current ranking for one user, ordered by rank ascending
        (rank 1 first) — what DigestService reads at send time now that
        ranking is computed on its own schedule (M9), not synchronously per
        digest run.
        """
        query = (
            self.db.query(UserRanking)
            .filter(UserRanking.user_id == user_id)
            .order_by(UserRanking.rank.asc())
        )
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def replace_for_user(
        self,
        user_id: int,
        ranked_scores: List,
        item_map: dict,
        score_version: str = "v0-curatoragent",
    ) -> int:
        """
        Wholesale-replace one user's ranking rows: delete everything they had,
        insert the fresh ranking. /feed always reflects the LATEST ranking
        run, not an ever-growing history.

        ranked_scores: List[RankedArticle] (app.ranking.types) — not
        imported here to avoid a circular import, see module docstring.
        item_map: digest_id -> DigestItem (same lookup used to build
        ranked_scores), used only to recover content_type/content_id from
        each RankedArticle's digest_id ("<article_type>:<db_id>").
        score_version: tagged onto every row this call writes (Principle 9) —
        lets the eval harness compare ranker versions and a formula change
        invalidate cleanly.
        """
        self.db.query(UserRanking).filter(UserRanking.user_id == user_id).delete()

        rows = []
        for ranked in ranked_scores:
            digest = item_map.get(ranked.digest_id)
            if digest is None:
                continue
            content_type = "youtube_video" if digest.article_type == "youtube" else "article"
            rows.append(UserRanking(
                user_id=user_id,
                content_type=content_type,
                content_id=digest.db_id,
                rank=ranked.rank,
                relevance_score=ranked.relevance_score,
                reasoning=ranked.reasoning or "",
                score_version=score_version,
                features=getattr(ranked, "features", None) or {},
            ))

        if rows:
            self.db.add_all(rows)
        self.db.commit()

        logger.info(f"UserRanking: replaced {len(rows)} rows for user_id={user_id}")
        return len(rows)
