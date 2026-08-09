# app/database/models/user_ranking.py
#
# Persists the OUTPUT of the ranking process so the Django web app can render
# a personalized feed without ever ranking synchronously from a web request.
# Written by the scheduled ranking task (app/tasks/ranking_tasks.py, M9 —
# previously written once per digest run by CuratorAgent, now decoupled from
# digest cadence per Architecture Principle 6); web/ only ever reads it (via
# web/apps/catalog/models.py's UserRanking mirror).
#
# One embedding table shares content_type/content_id across articles and
# youtube_videos (see embedding.py) — same polymorphic-association pattern
# here, since a ranked item is equally likely to be either.
#
# user_id is a PLAIN reference to Django's users.id, not a real FK — this
# table is owned by SQLAlchemy, but Django's users table isn't in this ORM's
# metadata at all. Same cross-ORM-by-convention pattern already used by
# UserExclusion.value (Django referencing a pipeline Source.key by string).
#
# M9: added score_version + features (mirrors content_score.py's existing
# pattern — Principle 7: log the feature vector that produced a score, not
# just the score, so it becomes training data for the eval harness / a
# future learned ranker). Both columns have a server_default so the ALTER
# doesn't break any rows already in the table from pre-M9 CuratorAgent runs.

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserRanking(Base):
    __tablename__ = "user_rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Django users.id — plain reference, no DB-level FK (different ORM/metadata)",
    )

    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="'article' or 'youtube_video'",
    )
    content_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Points to articles.id or youtube_videos.id, depending on content_type",
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="1 = most relevant to this user")
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
        comment="Templated 'why recommended' explanation built from the scoring features that won this rank — shown verbatim as 'Recommended because...'",
    )

    score_version: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="v0-curatoragent",
        comment="Which ranker/scoring-formula version produced this row — lets the eval harness compare versions and a formula change invalidate cleanly",
    )
    features: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, server_default="{}",
        comment="Exact per-item scoring feature snapshot (interest/topic match, quality score, freshness, source affinity, novelty penalty, MMR-selected flag, exploration-slice flag) — the eval harness and any future learned ranker train on this, not just relevance_score",
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        comment="When this ranking was produced — replaced wholesale on each ranking run, not accumulated",
    )

    __table_args__ = (
        # One rank per item per user for the CURRENT ranking pass — replaced
        # (not appended to) by UserRankingRepository.replace_for_user().
        UniqueConstraint("user_id", "content_type", "content_id", name="uq_user_ranking_content"),
        Index("ix_user_rankings_user_rank", "user_id", "rank"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserRanking user_id={self.user_id} content_type={self.content_type!r} "
            f"content_id={self.content_id} rank={self.rank}>"
        )
