# app/database/models/person_entity.py
#
# Links a person Entity (entity_type='person', M8) to their own scrapeable
# footprint (M10) — a blog, YouTube channel, GitHub, or Substack (arXiv
# author-specific tracking is deliberately out of scope: arXiv has no
# per-author feed mechanism the way the other four reduce to a plain RSS/
# Atom URL or a YouTube channel id; see docs/ROADMAP.md M10 and
# .wolf/cerebrum.md for the reasoning). `source_id` points at the actual
# Source Registry row that gets scraped for this footprint — reuses 100% of
# the existing scrape-dispatch mechanism (run_pipeline.py's
# run_scraping_phases()), no new ingestion machinery needed. Following the
# person itself needs NO new schema at all — that's just
# UserFollow(target_type="entity", target_key=str(entity.id)), already
# built in M9.

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PersonEntity(Base):
    __tablename__ = "person_entities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id"), nullable=False,
        comment="The person Entity this footprint belongs to (entities.entity_type should be 'person', not enforced at the DB level here)",
    )

    footprint_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="'blog' | 'youtube' | 'github' | 'substack' — a UI/data-modeling label; blog/github/substack all scrape via the same generic RSS/Atom mechanism (RssFeedScraper), only youtube uses a distinct per-channel adapter",
    )

    source_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sources.id"), nullable=True,
        comment="The Source Registry row that actually gets scraped for this footprint — null until the footprint has been validated/registered",
    )

    external_identifier: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Raw identifier as submitted (feed URL, YouTube channel id, GitHub username, etc.) — kept even after source_id is set, for display/audit",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("entity_id", "footprint_type", name="uq_person_entity_footprint"),
        CheckConstraint(
            "footprint_type IN ('blog', 'youtube', 'github', 'substack')",
            name="ck_person_entities_footprint_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<PersonEntity entity_id={self.entity_id} footprint_type={self.footprint_type!r}>"
