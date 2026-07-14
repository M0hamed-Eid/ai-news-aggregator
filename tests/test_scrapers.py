# tests/test_scrapers.py

# pytest automatically finds and runs functions that start with "test_"
# Run all tests with:  pytest tests/ -v

from app.scrapers.youtube_scraper import YouTubeScraper
from app.scrapers.base_scraper import ScrapedArticle
from datetime import datetime

# Matches the "youtube" row's config seeded by app/database/seed_sources.py —
# YouTubeScraper now takes channels/max_transcript_chars as explicit
# constructor args (Source Registry migration) instead of reading them from
# app.config. A small subset is enough for these tests.
TEST_CHANNELS = [
    {"name": "Andrej Karpathy", "channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
    {"name": "Yannic Kilcher", "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"},
]
TEST_MAX_TRANSCRIPT_CHARS = 8_000


def test_scraper_returns_list():
    """The scraper must always return a list, even if it's empty."""
    scraper = YouTubeScraper(channels=TEST_CHANNELS, max_transcript_chars=TEST_MAX_TRANSCRIPT_CHARS)
    result = scraper.scrape(hours_lookback=24)
    assert isinstance(result, list)


def test_articles_have_correct_shape():
    """Every returned item must be a ScrapedArticle with all required fields filled."""
    scraper = YouTubeScraper(channels=TEST_CHANNELS, max_transcript_chars=TEST_MAX_TRANSCRIPT_CHARS)
    articles = scraper.scrape(hours_lookback=72)  # wider window to guarantee results

    if len(articles) == 0:
        print("No articles in window — try increasing hours_lookback")
        return

    for article in articles:
        assert isinstance(article, ScrapedArticle)
        assert isinstance(article.title, str) and len(article.title) > 0
        assert isinstance(article.url, str) and article.url.startswith("http")
        assert isinstance(article.content, str) and len(article.content) > 0
        assert isinstance(article.published_at, datetime)
        assert article.source == "youtube"
        assert article.video_id is not None


def test_transcript_is_truncated():
    """Content should never exceed our configured max length."""
    scraper = YouTubeScraper(channels=TEST_CHANNELS, max_transcript_chars=TEST_MAX_TRANSCRIPT_CHARS)
    articles = scraper.scrape(hours_lookback=72)

    for article in articles:
        assert len(article.content) <= TEST_MAX_TRANSCRIPT_CHARS + 50
        # +50 accounts for the "... [transcript truncated]" suffix


def test_is_recent_helper():
    """Unit test for the base class time-filtering helper."""
    from app.scrapers.base_scraper import BaseScraper
    from datetime import timedelta, timezone

    # We can't instantiate BaseScraper directly (it's abstract),
    # but we can test its helper through the child class
    scraper = YouTubeScraper(channels=TEST_CHANNELS, max_transcript_chars=TEST_MAX_TRANSCRIPT_CHARS)

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    two_days_ago = now - timedelta(hours=48)

    assert scraper._is_recent(one_hour_ago, hours_lookback=24) is True
    assert scraper._is_recent(two_days_ago, hours_lookback=24) is False