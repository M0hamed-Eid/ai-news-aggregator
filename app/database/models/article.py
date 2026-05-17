# app/database/models/article.py
#
# Stores blog articles scraped from OpenAI and Anthropic.
# One table handles both sources — we distinguish them via the `source` column.

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Article(Base):
    """
    Represents a single blog post / news article from OpenAI or Anthropic.

    source values:
        "blog_openai"     — from OpenAI's RSS feed
        "blog_anthropic"  — scraped from anthropic.com/news via Playwright
    """

    __tablename__ = "articles"

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
    # Core content fields
    # -------------------------------------------------------------------------
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Article headline / title",
    )

    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        unique=True,       # enforced at DB level — no duplicate URLs ever
        comment="Canonical URL of the article",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Scraper source identifier, e.g. blog_openai | blog_anthropic",
    )

    author: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Author name or publishing organisation",
    )

    # Full article body (truncated to MAX_ARTICLE_CHARS by the scraper)
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full article text (may be truncated by the scraper)",
    )

    # AI-generated one-paragraph summary — populated by the curator agent
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="AI-generated summary (populated after scraping)",
    )

    # Comma-separated tags, e.g. "LLM,agents,safety"
    # Using a simple string is intentional — avoids a many-to-many join table
    # for now. Easy to migrate to a proper tags table later if needed.
    tags: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        default=None,
        comment="Comma-separated topic tags assigned by the curator agent",
    )

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the article was originally published",
    )

    # server_default uses a DB-level function so the timestamp is set by
    # PostgreSQL, not by the application. This is safer in multi-process setups.
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
        # Enforce only known source values at the DB level.
        CheckConstraint(
            "source IN ('blog_openai', 'blog_anthropic')",
            name="ck_articles_source",
        ),

        # Speed up date-range queries (e.g. "articles from the last 7 days")
        Index("ix_articles_published_at", "published_at"),

        # Speed up filtering by source (e.g. "all Anthropic articles")
        Index("ix_articles_source", "source"),

        # Partial index — speed up fetching articles that still need a summary
        Index(
            "ix_articles_summary_null",
            "id",
            postgresql_where="summary IS NULL",
        ),

        # Uniqueness constraint is already enforced by unique=True on the column,
        # but naming it explicitly makes error messages readable.
        UniqueConstraint("url", name="uq_articles_url"),
    )

    def __repr__(self) -> str:
        return (
            f"<Article id={self.id} source={self.source!r} "
            f"title={self.title[:60]!r}>"
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary (useful for logging and API responses)."""
        return {
            "id":           self.id,
            "title":        self.title,
            "url":          self.url,
            "source":       self.source,
            "author":       self.author,
            "summary":      self.summary,
            "tags":         self.tags,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at":   self.created_at.isoformat()   if self.created_at   else None,
        }