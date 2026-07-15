"""
Shared helpers threading save/hide/read state into content lists built by
apps.news's views. Kept here (not in apps.news) since SavedItem is owned by
this app.
"""
from django.utils import timezone

from .models import SavedItem, UserFollow


def _content_type_for(item) -> str:
    return "youtube_video" if hasattr(item, "video_id") else "article"


def attach_saved_state(user, items):
    """
    Mutates `items` in place, setting .is_saved/.is_hidden on each (Article
    or YoutubeVideo instance) from ONE bulk SavedItem query.

    Call this AFTER pagination has already sliced the list down to a single
    page — never on the full unpaginated queryset/list — so this only ever
    queries for items actually being displayed.
    """
    if not items:
        return items
    if not user.is_authenticated:
        for item in items:
            item.is_saved = False
            item.is_hidden = False
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
