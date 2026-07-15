# app/database/models/taxonomy_topic.py
#
# Controlled topic vocabulary (M8 — Content Intelligence Layer). ~27 rows,
# seeded via app/database/seed_taxonomy_topics.py (idempotent upsert-by-slug,
# same pattern as seed_sources.py). The 15 slugs matching web/apps/onboarding's
# seeded Interest rows are IDENTICAL on purpose — Django's Interest gets a
# taxonomy_topic FK (db_constraint=False, matched by slug in a data migration)
# so user interests and content topics share ONE vocabulary, per the roadmap.
# The remaining ~12 slugs have no Interest counterpart — too granular/
# technical for a user-facing "thing to follow" chip, but still valid content
# classification targets.
#
# Enum-constrained classification, not free-form tags: content_topics.taxonomy_topic_id
# is a real FK into this table, and EnrichmentAgent validates every LLM-returned
# topic slug against the live set of active rows here before persisting —
# never inventing a new slug on the fly.

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class TaxonomyTopic(Base):
    __tablename__ = "taxonomy_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Small fixed grouping for UI display, e.g. 'core-ai' | 'policy' | 'applications' | 'business' | 'infrastructure'",
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<TaxonomyTopic slug={self.slug!r} name={self.name!r}>"
