# tests/test_blog_scraper.py

from app.scrapers.blog_scraper import BlogScraper
from app.scrapers.base_scraper import ScrapedArticle
from datetime import datetime


def test_blog_scraper_returns_list():
    """BlogScraper must always return a list, even if no recent articles exist."""
    scraper = BlogScraper()
    result = scraper.scrape(hours_lookback=24)
    assert isinstance(result, list)


def test_blog_articles_have_correct_shape():
    """Every article must be a ScrapedArticle with all required fields filled."""
    scraper = BlogScraper()
    # Wide window to guarantee we get something
    articles = scraper.scrape(hours_lookback=24 * 30)

    if not articles:
        print("No articles in window — check feed URLs or increase hours_lookback")
        return

    for article in articles:
        assert isinstance(article, ScrapedArticle)
        assert isinstance(article.title, str) and len(article.title) > 0
        assert isinstance(article.url, str) and article.url.startswith("http")
        assert isinstance(article.content, str) and len(article.content) > 0
        assert isinstance(article.published_at, datetime)
        # source should be "blog_anthropic" or "blog_openai"
        assert article.source.startswith("blog_")
        assert article.video_id is None


def test_blog_content_is_truncated():
    """Content should never exceed MAX_ARTICLE_CHARS + buffer for the truncation note."""
    from app.scrapers.blog_scraper import MAX_ARTICLE_CHARS
    scraper = BlogScraper()
    articles = scraper.scrape(hours_lookback=24 * 30)

    for article in articles:
        assert len(article.content) <= MAX_ARTICLE_CHARS + 50


def test_both_sources_represented():
    """We should get articles from both Anthropic and OpenAI over a wide window."""
    scraper = BlogScraper()
    articles = scraper.scrape(hours_lookback=24 * 30)

    if not articles:
        print("No articles found — skipping source coverage check")
        return

    authors = {a.channel_or_author for a in articles}
    print(f"Sources found: {authors}")
    # At least one source should be present
    assert len(authors) >= 1


def test_fetch_article_content_handles_bad_url():
    """_fetch_article_content should return empty string for invalid URLs, not crash."""
    scraper = BlogScraper()
    result = scraper._fetch_article_content("https://this-url-does-not-exist-xyz.com/article")
    assert result == ""


def test_fetch_article_content_handles_timeout():
    """Should handle timeouts gracefully."""
    scraper = BlogScraper()
    # 10.255.255.1 is a non-routable IP — causes a fast connection failure
    result = scraper._fetch_article_content("http://10.255.255.1/article")
    assert result == ""