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
    # populated by later milestones, e.g.:
    # "unlimited_custom_sources": {User.Plan.PRO},
    # "deep_video_summaries": {User.Plan.PRO},
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
