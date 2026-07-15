# app/services/recipients.py
#
# Assembles the list of digest recipients for this pipeline run. Each active,
# non-paused Django user becomes a Recipient: a UserProfile (the exact shape
# RankingService/EmailAgent expect — see app/ranking/types.py)
# plus the extra per-user knobs those don't need to know about
# (max_items, excluded_categories, excluded_sources — used by DigestService
# to filter the shared content pool BEFORE ranking, not by the agents
# themselves).
#
# Reads Django's user/profile/interest/exclusion tables through the read-only
# cross-ORM mirror in app/database/models/django_readmodels.py — one bulk
# query with eager-loaded relationships, not one query per user.
#
# Backward-compatible fallback: if zero active, eligible users exist yet
# (today's actual state, before anyone registers through the web app), a
# single fallback Recipient is returned using UserProfile's own defaults and
# RECIPIENT_EMAIL/GMAIL_ADDRESS — today's exact single-recipient behavior.
# This keeps the pipeline fully functional before the first real signup.

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Set

from sqlalchemy.orm import Session, joinedload, selectinload

from app.ranking.types import UserProfile
from app.database.models.django_readmodels import DjangoUser, DjangoUserProfile
from app.database.repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)

# Sources deliberately outside the Source Registry (BlogScraper, hardcoded/
# legacy — see app/scrapers/blog_scraper.py) plus "youtube" as a safety net
# in case the registry query below fails — need a category for exclusion
# filtering even though they're not DB-driven sources.
_FALLBACK_SOURCE_CATEGORIES = {
    "blog_openai": "media",
    "blog_anthropic": "media",
    "youtube": "media",
}


@dataclass
class Recipient:
    """One digest recipient: a personalization profile plus content-pool filters."""
    profile: UserProfile
    max_items: int = 10
    excluded_categories: Set[str] = field(default_factory=set)
    excluded_sources: Set[str] = field(default_factory=set)
    # Django users.id — None only for the zero-active-users fallback recipient
    # (no real Django user to persist a ranking against). Used by
    # UserRankingRepository.replace_for_user() so web/'s /feed can read back
    # this recipient's ranking (frontend milestone, 2026-07-13).
    user_id: Optional[int] = None
    # Preferences v2 (M9) — real scoring inputs for RankingService, kept as
    # their own typed Recipient fields (not nested in UserProfile.preferences'
    # untyped dict) since they're new, ranking-specific knobs, not something
    # EmailAgent/the old CuratorAgent prompt ever read.
    format_balance: str = "balanced"
    topic_lean: str = "balanced"
    reading_time_budget_minutes: Optional[int] = None


def get_source_categories(db: Session) -> dict:
    """
    key -> category map, used to resolve a piece of content's Article.source
    string to a category for exclusion filtering. Sourced from the Source
    Registry (app/database/models/source.py), plus a small hardcoded fallback
    for the sources deliberately outside that registry.
    """
    categories = dict(_FALLBACK_SOURCE_CATEGORIES)
    try:
        for source in SourceRepository(db).get_active():
            categories[source.key] = source.category
    except Exception as exc:
        logger.warning("get_source_categories: failed to load Source Registry rows — %s", exc)
    return categories


def get_active_recipients(db: Session) -> List[Recipient]:
    """
    Return one Recipient per active Django user with non-paused digest
    settings, built from a single eager-loaded query (no N+1). Falls back to
    one single-recipient entry (RECIPIENT_EMAIL/GMAIL_ADDRESS, UserProfile
    defaults) if no active users exist yet.
    """
    recipients: List[Recipient] = []

    try:
        users = (
            db.query(DjangoUser)
            .join(DjangoUser.profile)
            .options(
                joinedload(DjangoUser.profile).joinedload(DjangoUserProfile.persona),
                joinedload(DjangoUser.profile).joinedload(DjangoUserProfile.digest_settings),
                joinedload(DjangoUser.profile).selectinload(DjangoUserProfile.interests),
                joinedload(DjangoUser.profile).selectinload(DjangoUserProfile.exclusions),
            )
            .filter(DjangoUser.is_active.is_(True))
            .all()
        )
    except Exception as exc:
        logger.error("get_active_recipients: failed to read Django user tables — %s", exc, exc_info=True)
        users = []

    for user in users:
        profile_row = user.profile
        if profile_row is None:
            continue  # should never happen (post_save signal always creates one), but be defensive

        settings = profile_row.digest_settings
        if settings is not None and settings.is_paused:
            continue

        interest_names = [ui.interest.name for ui in profile_row.interests] or None
        excluded_categories = {e.value for e in profile_row.exclusions if e.kind == "category"}
        excluded_sources = {e.value for e in profile_row.exclusions if e.kind == "source"}

        profile_kwargs = {
            "name": user.first_name or user.email.split("@")[0],
            "email": user.email,
        }
        if interest_names:
            profile_kwargs["interests"] = interest_names
        if settings is not None:
            profile_kwargs["expertise_level"] = settings.expertise_level
            profile_kwargs["preferences"] = {
                "content_depth": settings.content_depth,
                "preferred_sources": "all",
                "max_video_length": "any",
            }

        recipients.append(Recipient(
            profile=UserProfile(**profile_kwargs),
            max_items=(settings.max_items if settings is not None else 10),
            excluded_categories=excluded_categories,
            excluded_sources=excluded_sources,
            user_id=user.id,
            format_balance=(settings.format_balance if settings is not None else "balanced"),
            topic_lean=(settings.topic_lean if settings is not None else "balanced"),
            reading_time_budget_minutes=(settings.reading_time_budget_minutes if settings is not None else None),
        ))

    if recipients:
        return recipients

    # ── Fallback: no active users registered yet — preserve today's exact
    # single-recipient behavior so the pipeline stays fully functional before
    # the first real signup. ──────────────────────────────────────────────
    fallback_email = os.getenv("RECIPIENT_EMAIL") or os.getenv("GMAIL_ADDRESS", "")
    if not fallback_email:
        logger.warning(
            "get_active_recipients: no active users in the DB and no "
            "RECIPIENT_EMAIL/GMAIL_ADDRESS fallback configured — no recipients."
        )
        return []

    logger.info(
        "get_active_recipients: no active users found — falling back to "
        "single-recipient mode (%s)", fallback_email,
    )
    return [Recipient(profile=UserProfile(email=fallback_email), max_items=10)]
