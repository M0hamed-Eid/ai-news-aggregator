# tests/test_arxiv_scraper.py

from datetime import datetime

from app.scrapers.arxiv_scraper import ArxivScraper
from app.scrapers.base_scraper import ScrapedArticle

# Matches the "arxiv" row seeded by app/database/seed_sources.py — ArxivScraper
# now takes its category list as an explicit constructor arg (Source Registry
# migration) instead of reading it from app.config.
ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]


def test_arxiv_scraper_returns_list():
    scraper = ArxivScraper(categories=ARXIV_CATEGORIES)
    result = scraper.scrape(hours_lookback=24)
    assert isinstance(result, list)


def test_arxiv_articles_have_correct_shape():
    scraper = ArxivScraper(categories=ARXIV_CATEGORIES)
    articles = scraper.scrape(hours_lookback=24 * 7)  # wide window to guarantee results

    if not articles:
        print("No arXiv papers in window — try increasing hours_lookback")
        return

    for article in articles:
        assert isinstance(article, ScrapedArticle)
        assert isinstance(article.title, str) and len(article.title) > 0
        assert article.url.startswith("http")
        assert isinstance(article.content, str) and len(article.content) >= 50
        assert isinstance(article.published_at, datetime)
        assert article.source == "arxiv"
        assert article.video_id is None
        assert "(arXiv:" not in article.title  # id suffix stripped
        assert not article.content.lower().startswith("abstract:")  # prefix stripped