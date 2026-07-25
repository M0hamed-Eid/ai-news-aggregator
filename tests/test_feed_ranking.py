from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from apps.news.feed_ranking import diversify_home_items


@dataclass
class FeedItem:
    pk: int
    source: str
    published_at: datetime
    video_id: str | None = None


def _item(pk: int, source: str, hours_old: int, video_id: str | None = None) -> FeedItem:
    return FeedItem(
        pk=pk,
        source=source,
        published_at=datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc) - timedelta(hours=hours_old),
        video_id=video_id,
    )


def test_diversify_home_items_breaks_up_repeated_sources():
    items = [
        _item(1, "reddit", 0),
        _item(2, "reddit", 1),
        _item(3, "reddit", 2),
        _item(4, "github_release", 3),
        _item(5, "huggingface_model", 4),
    ]

    ranked = diversify_home_items(items, limit=5)

    assert ranked[0].source == "reddit"
    assert [item.source for item in ranked[:4]].count("reddit") == 2
    assert {item.source for item in ranked[:4]} == {"reddit", "github_release", "huggingface_model"}


def test_diversify_home_items_keeps_much_stronger_new_item_first():
    items = [
        _item(1, "reddit", 0),
        _item(2, "github_release", 24),
        _item(3, "huggingface_model", 26),
        _item(4, "reddit", 27),
    ]
    quality_scores = {
        ("article", 1): 1.0,
        ("article", 2): 0.1,
        ("article", 3): 0.1,
        ("article", 4): 0.1,
    }

    ranked = diversify_home_items(items, limit=4, quality_scores=quality_scores)

    assert ranked[0].source == "reddit"
    assert ranked[0].pk == 1


def test_diversify_home_items_treats_videos_as_youtube_source():
    items = [
        _item(1, "youtube", 0, video_id="v1"),
        _item(2, "youtube", 1, video_id="v2"),
        _item(3, "blog_openai", 2),
        _item(4, "youtube", 3, video_id="v3"),
    ]

    ranked = diversify_home_items(items, limit=4)

    assert ["youtube" if item.video_id else item.source for item in ranked] == [
        "youtube",
        "blog_openai",
        "youtube",
        "youtube",
    ]
