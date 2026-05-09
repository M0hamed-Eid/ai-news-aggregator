# app/scrapers/blog_scraper.py

# How this scraper works:
# Both Anthropic and OpenAI publish their news/research via RSS feeds.
# We use feedparser (same as the YouTube scraper) to get article metadata,
# then requests + convert to fetch the actual article content.
#
# Why not just use the RSS description?
# RSS descriptions are often truncated summaries (1-2 sentences).
# We want the full article text so the curator agent has enough content to work with.

import feedparser
import requests
import logging
from datetime import datetime, timezone
from typing import List

from html_to_markdown import convert

from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)


# Each blog source is a dict with:
#   name  — human-readable label (used in ScrapedArticle.channel_or_author)
#   feed  — RSS/Atom feed URL (feedparser handles both formats)
BLOG_SOURCES = [
    {
        "name": "Anthropic",
        "feed": "https://www.anthropic.com/rss.xml",
    },
    {
        "name": "OpenAI",
        "feed": "https://openai.com/news/rss.xml",
    },
]

# How many characters of article text to keep.
# Full articles can be 10,000–30,000+ characters — we truncate to keep LLM costs down.
MAX_ARTICLE_CHARS = 8000

# HTTP request timeout in seconds.
# Without this, a hanging server can block the whole pipeline indefinitely.
REQUEST_TIMEOUT = 10


class BlogScraper(BaseScraper):
    """
    Scrapes recent blog posts from AI company news pages (Anthropic, OpenAI).

    Strategy:
    1. Fetch RSS feed → get list of recent articles with metadata
    2. Filter by publish date (same _is_recent() helper from base class)
    3. Fetch each article's HTML → convert to Markdown → truncate
    4. Return list of ScrapedArticle objects (same shape as YouTube scraper)
    """

    def __init__(self):
        super().__init__(source_name="blog")
        self.sources = BLOG_SOURCES

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        """
        Main method — loops over all blog sources, returns flat list of articles.
        """
        all_articles = []

        for source in self.sources:
            logger.info(f"Scraping blog: {source['name']}")

            articles = self._scrape_source(source, hours_lookback)
            logger.info(f"  Found {len(articles)} recent articles from {source['name']}")

            all_articles.extend(articles)

        logger.info(f"Blog scraper finished. Total articles: {len(all_articles)}")
        return all_articles

    def _scrape_source(self, source: dict, hours_lookback: int) -> List[ScrapedArticle]:
        """
        Fetches and processes one blog source.
        Returns a list of ScrapedArticle objects for that source.
        """
        feed = feedparser.parse(source["feed"])

        if not feed.entries:
            logger.warning(
                f"No entries found for {source['name']}. "
                f"Feed URL may have changed: {source['feed']}"
            )
            return []

        articles = []

        for entry in feed.entries:
            # --- Parse publish date ---
            # feedparser normalizes most date formats into published_parsed (time.struct_time)
            # Some feeds use 'updated_parsed' instead — we fall back to that.
            time_struct = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )

            if time_struct is None:
                # No date at all — skip this entry (can't filter by recency)
                logger.warning(f"  No date found for entry: {entry.get('title', 'unknown')}")
                continue

            # Convert time.struct_time → datetime (UTC-aware)
            published_at = datetime(*time_struct[:6], tzinfo=timezone.utc)

            # Skip articles outside our lookback window
            if not self._is_recent(published_at, hours_lookback):
                continue

            # --- Fetch full article content ---
            url = entry.get("link", "")
            if not url:
                logger.warning(f"  No URL for entry: {entry.get('title', 'unknown')}")
                continue

            content = self._fetch_article_content(url)

            # If we couldn't fetch the article, fall back to the RSS summary.
            # The summary is short but better than nothing for the curator agent.
            if not content:
                content = entry.get("summary", "")
                if content:
                    logger.info(f"  Using RSS summary as fallback for: {entry.title}")

            # Skip entries with no content at all
            if not content:
                logger.warning(f"  No content available for: {entry.get('title', 'unknown')}")
                continue

            articles.append(
                ScrapedArticle(
                    title=entry.get("title", "Untitled"),
                    url=url,
                    content=content,
                    source=f"{self.source_name}_{source['name'].lower()}",  # e.g. "blog_anthropic"
                    channel_or_author=source["name"],
                    published_at=published_at,
                    video_id=None,  # not a video
                )
            )

        return articles

    def _fetch_article_content(self, url: str) -> str:
        """
        Fetches a web page and converts its HTML to clean Markdown text.

        Why Markdown instead of raw HTML?
        - HTML has tons of nav menus, footers, ads, script tags — noise for the LLM
        - Markdown gives us just the readable text with basic structure preserved
        - convert handles the conversion cleanly

        Returns empty string on any failure (network error, timeout, bad response).
        """
        try:
            headers = {
                # Some sites block requests without a user-agent (they think it's a bot).
                # A realistic browser user-agent gets us through in most cases.
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI-News-Aggregator/1.0; "
                    "+https://github.com/your-repo)"
                )
            }

            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            # raise_for_status() throws an exception for 4xx/5xx responses
            # so we don't silently process error pages as content
            response.raise_for_status()

            # Convert HTML → Markdown
            # convert strips tags, preserves headings/lists/links as text
            markdown_text = convert(response.text)

            # Truncate to avoid sending huge prompts to the LLM later
            if len(markdown_text) > MAX_ARTICLE_CHARS:
                markdown_text = markdown_text[:MAX_ARTICLE_CHARS] + "... [article truncated]"

            return markdown_text.strip()

        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout fetching article: {url}")
            return ""

        except requests.exceptions.HTTPError as e:
            logger.warning(f"  HTTP error {e.response.status_code} for: {url}")
            return ""

        except requests.exceptions.RequestException as e:
            # Covers ConnectionError, TooManyRedirects, etc.
            logger.error(f"  Request failed for {url}: {e}")
            return ""

        except Exception as e:
            # Catch-all — convert can raise unexpected errors on malformed HTML
            logger.error(f"  Unexpected error processing {url}: {e}")
            return ""