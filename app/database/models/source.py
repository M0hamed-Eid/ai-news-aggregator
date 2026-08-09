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
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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

    User-submitted sources (M10): visibility='user' rows are gated by an
    AI-relevance check at creation (see app/services/relevance_gate.py) and
    re-validated monthly (feeds drift); their content only reaches a user's
    feed/ranking/digest via an active Django user_source_subscriptions row
    (opt-in), unlike visibility='global' rows (on by default for everyone,
    opt-out via UserExclusion — unchanged since M4). schedule_hours is
    ACTUALLY enforced (not just metadata) for visibility='user' rows only —
    see run_pipeline.py's run_scraping_phases(); the 9 curated rows keep
    their existing every-pipeline-run behavior untouched.
    """

    __tablename__ = "sources"

    # -------------------------------------------------------------------------
    # Primary key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="Auto-incrementing surrogate key. SQLite variant is Integer, not BigInteger -- see app/database/models/article.py's id column comment for why.",
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
        JSON().with_variant(JSONB(), "postgresql"),
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
    # User-submitted sources (M10) — all nullable/defaulted so every
    # pre-M10 row (the 9 admin-seeded sources) is unaffected. visibility
    # distinguishes the curated registry (on-by-default for everyone,
    # opt-out via UserExclusion — unchanged from M4) from user-submitted
    # sources (opt-IN via Django's user_source_subscriptions — see
    # web/apps/onboarding/models.py). feed_url is the canonicalization key:
    # before creating a new user-submitted Source row, check whether one
    # already exists for this exact feed URL — "the same feed added by two
    # users creates one global[sic, roadmap's own wording for "one shared"]
    # source, two subscriptions", per the roadmap's M10 success criterion.
    # -------------------------------------------------------------------------
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Django users.id of whoever submitted this source — plain reference, no DB-level FK (different ORM/metadata). Null for the 9 admin-seeded sources.",
    )

    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="global",
        server_default="global",
        comment="'global' (admin-seeded, on by default for everyone) or 'user' (submitted by a user, opt-in via user_source_subscriptions)",
    )

    feed_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        default=None,
        unique=True,
        comment="Canonicalization key for user-submitted RSS sources — the exact feed URL, so re-submitting an already-known feed reuses the existing Source row instead of duplicating it. Null for admin-seeded rows (their feeds live inside config['feeds'], several per row).",
    )

    validation_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
        comment="AI-relevance gate outcome for user-submitted sources: 'accepted' | 'accepted_low_trust' | 'rejected'. Null for admin-seeded rows (never gated).",
    )

    validation_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="Mean cosine similarity vs. the AI-corpus centroid at last validation — the relevance gate's raw score, not just its accept/reject decision",
    )

    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="When the relevance gate last ran for this source — re-validated monthly per the roadmap (feeds drift over time)",
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
        CheckConstraint(
            "visibility IN ('global', 'user')",
            name="ck_sources_visibility",
        ),
        CheckConstraint(
            "validation_status IS NULL OR validation_status IN ('accepted', 'accepted_low_trust', 'rejected')",
            name="ck_sources_validation_status",
        ),
        Index("ix_sources_is_active", "is_active"),
        Index("ix_sources_category", "category"),
        Index("ix_sources_visibility", "visibility"),
        Index("ix_sources_created_by", "created_by"),
    )

    def __repr__(self) -> str:
        return (
            f"<Source id={self.id} key={self.key!r} "
            f"category={self.category!r} active={self.is_active}>"
        )
