"""
Thin entitlement gate: user_can(user, feature) reads User.plan.

Used nowhere yet (M6 — Infrastructure Foundation only builds the scaffold);
later milestones register real feature keys here as they add Pro-gated
surfaces (custom source caps, deep video summaries, alerts, ...).

FEATURE_PLANS is fail-closed by design: a feature name that isn't a key here
is unavailable to EVERYONE, not granted to everyone. A typo'd feature string
must never silently unlock a paid feature — the safe default for a
billing-adjacent check is "locked until someone deliberately adds it."
"""

from django.utils import timezone

from .models import User

FEATURE_PLANS: dict[str, set[str]] = {
    # M10 — Free accounts cap at FREE_CUSTOM_SOURCE_LIMIT (see
    # apps.onboarding.source_submission); Pro is unlimited. Matches the
    # roadmap's own M13 Free-vs-Pro table ("Custom sources | 3 | Unlimited").
    "unlimited_custom_sources": {User.Plan.PRO},
    # M11 — the weekly grounded trend narrative (/insights/) is the first
    # full-page Pro gate in this app (see web/apps/news/views.py::TrendReportView).
    "trend_narrative": {User.Plan.PRO},
    # M12 — chaptered/deep summaries for long-form video (see
    # web/apps/news/views.py::VideoDetailView). Gates the UI section only —
    # chunking/chaptering is computed for every qualifying video regardless
    # of any viewer's plan (Architecture Principle 1).
    "deep_video_summaries": {User.Plan.PRO},
    # M13 — found via audit: docs/ROADMAP.md's Free/Pro table has always
    # promised "People follows: few (Free) / Unlimited (Pro)", but no cap
    # was ever implemented when follow/unfollow shipped in M9 (see
    # web/apps/behavior/views.py::FollowToggleView, FREE_FOLLOW_LIMIT).
    "unlimited_follows": {User.Plan.PRO},
    # M14 — RAG chat assistant. Free accounts still get real access (see
    # apps.assistant.views.FREE_DAILY_MESSAGE_LIMIT for the numeric cap,
    # same boolean-entitlement + counter shape as unlimited_follows above);
    # Pro is unlimited.
    "ai_assistant_unlimited": {User.Plan.PRO},
}


def user_can(user: User, feature: str) -> bool:
    """
    True if `user`'s current plan grants `feature`.

    An expired Pro plan (plan_expires_at in the past) is treated as Free —
    entitlements always reflect the user's EFFECTIVE plan, not the stored
    label.
    """
    allowed_plans = FEATURE_PLANS.get(feature)
    if not allowed_plans:
        return False  # unregistered feature => locked for everyone

    effective_plan = user.plan
    if (
        effective_plan == User.Plan.PRO
        and user.plan_expires_at is not None
        and user.plan_expires_at < timezone.now()
    ):
        effective_plan = User.Plan.FREE

    return effective_plan in allowed_plans
