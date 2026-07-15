# app/database/repositories/digest_click_token_repository.py
#
# Mints DigestClickToken rows at digest-build time (app/services/digest_service.py).
# INSERT-ONLY — never upserted. See app/database/models/digest_click_token.py's
# module docstring: a later digest send must not invalidate a token still
# sitting in an already-delivered email.

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from sqlalchemy import func

from app.database.models.digest_click_token import DigestClickToken
from app.database.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class DigestClickTokenRepository(BaseRepository[DigestClickToken]):

    def __init__(self, db) -> None:
        super().__init__(db, DigestClickToken)

    def get_last_shown_at(self, user_id: int, days: int = 30) -> Dict[Tuple[str, int], datetime]:
        """
        {(content_type, content_id): most_recent_created_at} for everything
        minted into a digest for this user in the last `days` — the ranker's
        novelty-penalty feature reads this (M9): an item shown recently gets
        penalized so the same top item doesn't monopolize every ranking run;
        the penalty fades as that history ages.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            self.db.query(
                DigestClickToken.content_type,
                DigestClickToken.content_id,
                func.max(DigestClickToken.created_at),
            )
            .filter(DigestClickToken.user_id == user_id, DigestClickToken.created_at >= cutoff)
            .group_by(DigestClickToken.content_type, DigestClickToken.content_id)
            .all()
        )
        return {(content_type, content_id): last_shown for content_type, content_id, last_shown in rows}

    def mint_for_recipient(
        self, user_id: int, items: List[Tuple[str, int]],
    ) -> Dict[Tuple[str, int], str]:
        """
        Insert one fresh token per (content_type, content_id) pair, return a
        {(content_type, content_id): token} map. `items` should be ONLY the
        items that actually made this recipient's email (post rank[:limit]
        slicing) — not the whole filtered candidate pool.
        """
        rows = [
            DigestClickToken(user_id=user_id, content_type=content_type, content_id=content_id)
            for content_type, content_id in items
        ]
        if not rows:
            return {}
        self.db.add_all(rows)
        self.db.commit()
        token_map = {(r.content_type, r.content_id): r.token for r in rows}
        logger.info("DigestClickToken: minted %d token(s) for user_id=%s", len(rows), user_id)
        return token_map
