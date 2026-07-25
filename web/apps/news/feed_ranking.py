"""Home-feed ranking helpers shared by API views and tests."""

from __future__ import annotations

from typing import Callable

HOME_FRESHNESS_HALFLIFE_HOURS = 48.0
HOME_QUALITY_WEIGHT = 0.35
HOME_SOURCE_COUNT_PENALTY = 0.08
HOME_SOURCE_CONSECUTIVE_PENALTY = 0.18
HOME_MAX_CONSECUTIVE_SOURCE = 2


def source_key_for_item(item) -> str:
    return "youtube" if getattr(item, "video_id", None) else item.source


def content_type_for_item(item) -> str:
    return "youtube_video" if getattr(item, "video_id", None) else "article"


def home_base_score(item, quality_score: float, newest_published_at) -> float:
    age_hours = max(0.0, (newest_published_at - item.published_at).total_seconds() / 3600.0)
    freshness = 0.5 ** (age_hours / HOME_FRESHNESS_HALFLIFE_HOURS)
    quality = max(0.0, min(1.0, quality_score))
    return (1.0 - HOME_QUALITY_WEIGHT) * freshness + HOME_QUALITY_WEIGHT * quality


def diversify_home_items(
    items: list,
    limit: int,
    quality_scores: dict | None = None,
    source_key: Callable[[object], str] = source_key_for_item,
) -> list:
    """Greedy source diversification over a recency+quality pre-ranked page."""
    page = list(items[:limit])
    if len(page) <= 1:
        return page

    quality_scores = quality_scores or {}
    newest_published_at = max(item.published_at for item in page)
    pool = [
        (
            item,
            home_base_score(
                item,
                quality_scores.get((content_type_for_item(item), item.pk), 0.5),
                newest_published_at,
            ),
        )
        for item in page
    ]
    selected = []
    source_counts = {}

    while pool and len(selected) < limit:
        best_idx, best_score = None, None
        last_source = source_key(selected[-1]) if selected else None
        run_length = 0
        for previous in reversed(selected):
            if source_key(previous) != last_source:
                break
            run_length += 1

        for idx, (item, base_score) in enumerate(pool):
            source = source_key(item)
            penalty = source_counts.get(source, 0) * HOME_SOURCE_COUNT_PENALTY
            if source == last_source:
                penalty += HOME_SOURCE_CONSECUTIVE_PENALTY
                if run_length >= HOME_MAX_CONSECUTIVE_SOURCE:
                    penalty += HOME_SOURCE_CONSECUTIVE_PENALTY
            score = base_score - penalty
            if best_score is None or score > best_score:
                best_idx, best_score = idx, score

        item, _ = pool.pop(best_idx)
        selected.append(item)
        source = source_key(item)
        source_counts[source] = source_counts.get(source, 0) + 1

    return selected
