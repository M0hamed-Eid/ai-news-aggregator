# app/config.py
#
# Single source of truth for all project settings.
#
# Changes from original
# ---------------------
# 1. Added UserProfile.expertise_level and UserProfile.preferences so the
#    curator agent has richer context to rank content — these fields were
#    referenced in the original curator_agent.py but missing from config.
# 2. Added UserProfile.email so DigestService knows where to send the digest
#    without hard-coding an address in run_pipeline.py.
# 3. No breaking changes to existing fields.
# 4. Fixed a duplicate ScraperConfig class definition — the second (winning)
#    copy had a stub `youtube_channels` list (just a comment, no entries),
#    silently zeroing out YouTube ingestion. Merged into one class carrying
#    the real channel list + arxiv_categories, and added github_repos.
# 5. Added reddit_feeds / government_feeds / funding_feeds (each a list of
#    plain feed-definition dicts consumed by the generic RssFeedScraper —
#    see app/scrapers/rss_feed_scraper.py) plus federal_register_terms and
#    huggingface_fetch_limit for the two API-based adapters. Adding another
#    pure-RSS source later is just another dict in the relevant list here —
#    no new scraper code required.
# 6. REMOVED reddit_feeds, government_feeds, funding_feeds, github_repos,
#    arxiv_categories, youtube_channels, federal_register_terms,
#    huggingface_fetch_limit, and max_transcript_chars from ScraperConfig —
#    these per-source settings moved to the DB-driven Source Registry
#    (`sources` table, app/database/models/source.py), backfilled via
#    app/database/seed_sources.py. Scrapers now receive these values as
#    explicit constructor arguments (built from a Source row's .config by
#    run_pipeline.py's HANDLER_BUILDERS) instead of reading this file.
# 7. REMOVED UserProfile and AppConfig.user entirely. This was the last
#    piece of business data living in application config — a single
#    hardcoded "the one person this pipeline serves" object. Personalization
#    is now per-user, sourced from the Django-owned users/user_profiles/
#    personas/interests/user_interests/user_digest_settings/user_exclusions
#    tables (see app/database/models/django_readmodels.py, a read-only
#    cross-ORM mirror) and assembled into a UserProfile instance PER
#    RECIPIENT by app/services/recipients.py — UserProfile the dataclass
#    still exists (as a type contract EmailAgent/RankingService expect),
#    just relocated to app/agents/curator_agent.py since that's where it was
#    consumed at the time. This file now holds only infrastructure settings,
#    per the project's "config = infra, DB = business data" rule.
# 8. [M9] CuratorAgent (and app/agents/curator_agent.py itself) is now
#    deleted — UserProfile/DigestItem/RankedArticle moved on again, to the
#    LLM-agnostic app/ranking/types.py, since ranking is no longer LLM-based
#    (see app/services/ranking_service.py).

from dataclasses import dataclass, field


@dataclass
class ScraperConfig:
    """
    Controls how scrapers behave.
    hours_lookback = how far back to fetch videos (24 = last 24 hours).

    Per-source settings (which subreddits, which arXiv categories, YouTube
    channel list, etc.) used to live here as individual fields. They now live
    in the DB-driven Source Registry (`sources` table — see
    app/database/models/source.py) instead, backfilled via
    app/database/seed_sources.py. See "Changes from original" item 6 above.
    """
    hours_lookback: int = 24


@dataclass
class AppConfig:
    """
    Top-level config object. Import this anywhere in the project.

    Usage:
        from app.config import config
    """
    scraper: ScraperConfig = field(default_factory=ScraperConfig)


# Single instance — import this everywhere
config = AppConfig()