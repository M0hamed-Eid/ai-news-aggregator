# app/database/models/content_enrichment.py
#
# ONE row per content item, holding everything EnrichmentAgent's single
# structured LLM call produces beyond the plain title/summary already stored
# on Article/YoutubeVideo (M8 — Content Intelligence Layer, Principle 4:
# "one enrichment call per item"). Upserted (not appended) — content_category/
# technical_depth/etc. reflect the LATEST enrichment pass for this item.
#
# Named `content_category` (NOT `content_type`) deliberately: `content_type`
# already means "article" vs "youtube_video" everywhere else in this codebase
# (Embedding, UserRanking, DigestClickToken, UserEvent, SavedItem, and the
# content_type/content_id key pair on THIS table too) — a third meaning under
# the identical name would be a real readability trap, worse for landing on
# the same table as an actual (content_type, content_id) pair.

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ContentEnrichment(Base):
    __tablename__ = "content_enrichment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="'article' or 'youtube_video'")
    content_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    content_category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="'research' | 'product-launch' | 'tutorial' | 'opinion' | 'funding' | 'announcement' | 'tooling' | 'other'",
    )
    technical_depth: Mapped[int] = mapped_column(Integer, nullable=False, comment="1 (accessible) - 5 (expert/research-level)")

    key_points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, comment="List[str] — 3-5 short bullet takeaways")
    technical_details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_angle: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")

    enrichment_version: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Prompt/schema version tag (app/agents/enrichment_agent.py's ENRICHMENT_VERSION) — distinguishes e.g. live-ingest vs. backfill passes",
    )
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("content_type", "content_id", name="uq_content_enrichment"),
        CheckConstraint(
            "content_category IN ("
            "'research', 'product-launch', 'tutorial', 'opinion', "
            "'funding', 'announcement', 'tooling', 'other'"
            ")",
            name="ck_content_enrichment_category",
        ),
        CheckConstraint("technical_depth BETWEEN 1 AND 5", name="ck_content_enrichment_depth"),
    )

    def __repr__(self) -> str:
        return f"<ContentEnrichment {self.content_type}:{self.content_id} category={self.content_category!r}>"
