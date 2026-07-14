# app/database/models/digest_log.py
#
# One row per digest email actually sent to a user. Exists so the Django web
# app can show "digests received: N" on the profile page WITHOUT the pipeline
# ever writing into a Django-owned table (user_digest_settings) — that would
# break the project's cross-ORM rule (each ORM writes only its own tables;
# reads go both ways via read-only mirrors, writes never cross). This table
# is owned/written by the pipeline (run_pipeline.py's run_digest_phase, after
# a successful EmailSender.send()); Django only ever reads it, via
# web/apps/catalog/models.py's DigestLog mirror.
#
# user_id is a plain reference to Django's users.id, same convention as
# UserRanking.user_id / UserExclusion.value — no real cross-ORM FK.

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DigestLog(Base):
    __tablename__ = "digest_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Django users.id — plain reference, no DB-level FK (different ORM/metadata)",
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_digest_log_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<DigestLog user_id={self.user_id} sent_at={self.sent_at}>"
