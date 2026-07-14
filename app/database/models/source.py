# app/database/models/source.py
#
# Source Registry — DB-driven replacement for the hardcoded per-source config
# that used to live in ScraperConfig (app/config.py). Each row describes one
# ingestion source (which category it belongs to, which adapter runs it, and
# that adapter's config blob) so that adding/disabling/reconfiguring a source
# is a data change (see app/database/seed_sources.py), not a code change.
#
# key values (must match the Article.source / YoutubeVideo.source values the
# corresponding scraper emits — see app/database/models/article.py's docstring
# for the full list):
#   "arxiv", "github_release", "youtube", "reddit", "government_us",
#   "government_uk", "government_nist", "funding_crunchbase",
#   "huggingface_model"
#
# Note: blog_openai/blog_anthropic (BlogScraper) are deliberately NOT in this
# registry — BlogScraper stays hardcoded/legacy for this milestone.

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Source(Base):
    """
    Represents a single ingestion source and how to run it.

    category values:
        "research", "open_source", "product_model_databases",
        "developer_communities", "government", "funding", "media"

    adapter_type values:
        "rss"    — generic RssFeedScraper, config["feeds"] is a list of
                   feed-definition dicts (see rss_feed_scraper.py). `handler`
                   is unused for these rows.
        "api"    — a bespoke BaseScraper subclass keyed by `handler` (see
                   HANDLER_BUILDERS in run_pipeline.py), config is that
                   scraper's constructor kwargs.
        "search" — reserved for a future search-based adapter (not used yet).
        "scrape" — reserved for a future browser-scrape adapter (not used yet).
    """

    __tablename__ = "sources"

    # -------------------------------------------------------------------------
    # Primary key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Auto-incrementing surrogate key",
    )

    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Stable identifier, matches Article.source/YoutubeVideo.source values (e.g. 'reddit', 'arxiv')",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable display name (e.g. 'arXiv', 'US Federal Register')",
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Content category — see class docstring for the full list of valid values",
    )

    adapter_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Which kind of adapter runs this source — see class docstring for the full list of valid values",
    )

    handler: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
        comment="Python registry key for non-generic adapters (HANDLER_BUILDERS in run_pipeline.py); only meaningful when adapter_type != 'rss', null/unused for rss rows",
    )

    # -------------------------------------------------------------------------
    # Adapter configuration
    # -------------------------------------------------------------------------
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Adapter-specific config blob — e.g. {'categories': [...]} for arxiv, {'feeds': [...]} for rss",
    )

    schedule_hours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Desired cadence in hours — metadata only, not a real background scheduler",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this source should be included in scraping runs",
    )

    # -------------------------------------------------------------------------
    # Run tracking
    # -------------------------------------------------------------------------
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Last time this source was attempted (success or failure)",
    )

    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Last time this source completed a run without error",
    )

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this record was first inserted into our DB",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last time any field on this record was changed",
    )

    # -------------------------------------------------------------------------
    # Table-level constraints and indexes
    # -------------------------------------------------------------------------
    __table_args__ = (
        CheckConstraint(
            "category IN ("
            "'research', 'open_source', 'product_model_databases', "
            "'developer_communities', 'government', 'funding', 'media'"
            ")",
            name="ck_sources_category",
        ),
        CheckConstraint(
            "adapter_type IN ('rss', 'api', 'search', 'scrape')",
            name="ck_sources_adapter_type",
        ),
        Index("ix_sources_is_active", "is_active"),
        Index("ix_sources_category", "category"),
    )

    def __repr__(self) -> str:
        return (
            f"<Source id={self.id} key={self.key!r} "
            f"category={self.category!r} active={self.is_active}>"
        )
