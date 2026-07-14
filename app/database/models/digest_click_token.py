# app/database/models/digest_click_token.py
#
# One row per (recipient, item) minted when a digest email is built (M7) —
# lets a digest link point at a tracked redirect (Django's DigestRedirectView,
# GET /r/<token>/) instead of the raw external URL, so digest CTR becomes
# measurable, without inventing a shared-secret/signing scheme across the
# pipeline/Django process+venv boundary. Django looks tokens up read-only via
# web/apps/catalog/models.py's DigestClickToken mirror, logs a digest_click
# UserEvent (its own table, own write), then redirects to the real content URL
# (resolved from its own Article/YoutubeVideo mirror by content_id, never by
# trusting an embedded URL).
#
# INSERT-ONLY, never upserted: a later digest send must not invalidate a
# token still sitting in an already-delivered email. Old rows are pruned by
# the same 90-day retention pass that prunes user_events (see
# app/tasks/affinity_tasks.py) — no expiry logic needed here, just cleanup.
#
# user_id is a plain reference to Django's users.id, same convention as
# UserRanking.user_id / DigestLog.user_id — no real cross-ORM FK.

import secrets
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _generate_token() -> str:
    return secrets.token_urlsafe(16)


class DigestClickToken(Base):
    __tablename__ = "digest_click_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, default=_generate_token)

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Django users.id — plain reference, no DB-level FK (different ORM/metadata)",
    )
    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_digest_click_tokens_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DigestClickToken token={self.token} user_id={self.user_id} {self.content_type}:{self.content_id}>"
