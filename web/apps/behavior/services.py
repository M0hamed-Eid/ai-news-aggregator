"""
Shared helpers threading save/hide/read state into content lists built by
apps.news's views. Kept here (not in apps.news) since SavedItem is owned by
this app.
"""
from django.utils import timezone

from apps.accounts.entitlements import user_can

from .models import SavedItem, UserFollow

# M13 — found via audit: promised in docs/ROADMAP.md's Free/Pro table since
# before M9 shipped follow/unfollow, never actually enforced until now.
# Mirrors FREE_CUSTOM_SOURCE_LIMIT's exact pattern (apps.onboarding.source_submission).
FREE_FOLLOW_LIMIT = 20


def _content_type_for(item) -> str:
    return "youtube_video" if hasattr(item, "video_id") else "article"


def attach_saved_state(user, items):
    """
    Mutates `items` in place, setting .is_saved/.is_hidden/.is_read on each
    (Article or YoutubeVideo instance) from ONE bulk SavedItem query.

    Call this AFTER pagination has already sliced the list down to a single
    page — never on the full unpaginated queryset/list — so this only ever
    queries for items actually being displayed.

    .is_read was added alongside the M15 frontend integration's JSON API
    (apps.news.serializers) — every existing template caller already ignores
    unused attributes on these objects, so adding it here is a no-op for them.
    """
    if not items:
        return items
    if not user.is_authenticated:
        for item in items:
            item.is_saved = False
            item.is_hidden = False
            item.is_read = False
        return items

    keys = [(_content_type_for(item), item.pk) for item in items]
    content_types = {k[0] for k in keys}
    content_ids = {k[1] for k in keys}
    saved_by_key = {
        (s.content_type, s.content_id): s
        for s in SavedItem.objects.filter(
            user=user, content_type__in=content_types, content_id__in=content_ids,
        )
    }
    for item, key in zip(items, keys):
        state = saved_by_key.get(key)
        item.is_saved = bool(state and state.is_saved)
        item.is_hidden = bool(state and state.is_hidden)
        item.is_read = bool(state and state.is_read)
    return items


def get_followed_keys(user, target_type: str) -> set:
    """
    Set of target_keys this user follows for one target_type ("entity",
    "topic", or "source") — used by templates to render a chip's follow
    button in the already-followed state (Phase 6: entity/topic chips on
    detail pages) without an N+1 query per chip.
    """
    if not user.is_authenticated:
        return set()
    return set(
        UserFollow.objects.filter(user=user, target_type=target_type)
        .values_list("target_key", flat=True)
    )


def toggle_follow(user, target_type: str, target_key: str) -> dict:
    """
    Delete-or-create a UserFollow row, enforcing FREE_FOLLOW_LIMIT for
    non-unlimited-follow users. Returns {"following": bool} on success, or
    {"error": str} (caller sets HTTP 403) if the free-tier cap is hit.

    Extracted for apps.behavior.api_views.FollowToggleAPIView (the real
    endpoint the SPA calls) — apps.behavior.views.FollowToggleView (the
    legacy endpoint, still called by web/static/js/beacon.js today) keeps
    its own independent inline copy of this same cap/toggle logic rather
    than being refactored to call this, since that whole legacy view is
    slated for removal once beacon.js is retired (M15 Phase 5) and isn't
    worth churning in the meantime.
    """
    target_key = str(target_key)[:200]
    deleted, _ = UserFollow.objects.filter(user=user, target_type=target_type, target_key=target_key).delete()
    if deleted:
        return {"following": False}

    if not user_can(user, "unlimited_follows"):
        current_count = UserFollow.objects.filter(user=user).count()
        if current_count >= FREE_FOLLOW_LIMIT:
            return {"error": f"Free accounts can follow up to {FREE_FOLLOW_LIMIT} — upgrade to Pro for unlimited."}

    UserFollow.objects.create(user=user, target_type=target_type, target_key=target_key)
    return {"following": True}


def mark_read(user, content_type: str, content_id: int) -> None:
    """
    Idempotent "this user has read this item" signal — called from
    ArticleDetailView/VideoDetailView on GET. A server-side detail-page hit
    is a sufficient, simple read signal for M7 (no client-side dwell
    threshold needed for v1 — that's a future enhancement, not required by
    the roadmap's stated success criteria).
    """
    if not user.is_authenticated:
        return
    item, _ = SavedItem.objects.get_or_create(user=user, content_type=content_type, content_id=content_id)
    if not item.is_read:
        item.is_read = True
        item.read_at = timezone.now()
        item.save(update_fields=["is_read", "read_at", "updated_at"])
