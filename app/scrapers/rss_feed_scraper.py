# app/scrapers/rss_feed_scraper.py
#
# Generic, configuration-driven RSS/Atom feed scraper. Adding a new pure-RSS
# source should require ONLY a new row in the Source Registry (`sources`
# table — see app/database/models/source.py, seeded via
# app/database/seed_sources.py) with adapter_type="rss" and a config["feeds"]
# list — no new Python code. Currently reused across Developer Communities
# (Reddit), Government (UK gov.uk, NIST), and Funding (Crunchbase News).
#
# The field-extraction logic below was validated against three structurally
# different real feeds (arXiv RSS 2.0, GitHub Atom, WordPress RSS 2.0):
# title/link/author/summary/tags are always safe to read with .get(), but
# the published date and full body need a fallback chain — that's exactly
# what _parse_published/_extract_body do.

import logging
import re
import time
from datetime import datetime, timezone
from typing import List, Optional

import feedparser

from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTENT_CHARS = 8000

_TAG_RE = re.compile(r"<[^>]+>")


class RssFeedScraper(BaseScraper):
    """
    feeds: list of dicts, each describing one feed to poll:
      {
        "url": str,                  # required — feed URL
        "source": str,               # required — Article.source value for its items
        "label": str,                # optional — channel_or_author override
                                      #   (defaults to the entry's own author, then the feed's title)
        "headers": dict,             # optional — custom request headers (e.g. a required User-Agent)
        "delay_after_seconds": float,# optional — pause after fetching this feed, default 0
        "filter_keywords": [str],    # optional — keep only entries whose title+body match one
                                      #   keyword (word-boundary, case-insensitive) — use this when
                                      #   the feed itself has no working topic filter
        "max_content_chars": int,    # optional — per-feed content truncation, default 8000
      }
    """

    def __init__(self, source_name: str, feeds: List[dict]):
        super().__init__(source_name=source_name)
        self.feeds = feeds

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles: List[ScrapedArticle] = []

        for i, feed_cfg in enumerate(self.feeds):
            url = feed_cfg["url"]
            source = feed_cfg["source"]
            label = feed_cfg.get("label")
            headers = feed_cfg.get("headers")
            keywords = feed_cfg.get("filter_keywords")
            max_chars = feed_cfg.get("max_content_chars", DEFAULT_MAX_CONTENT_CHARS)

            logger.info(f"Scraping RSS feed [{source}]: {url}")
            try:
                feed = feedparser.parse(url, request_headers=headers) if headers else feedparser.parse(url)

                if not feed.entries:
                    logger.warning(f"No entries for feed [{source}] {url}")
                else:
                    feed_title = feed.feed.get("title", "") if hasattr(feed, "feed") else ""
                    found = 0

                    for entry in feed.entries:
                        published_at = self._parse_published(entry)
                        if published_at is None or not self._is_recent(published_at, hours_lookback):
                            continue

                        link = entry.get("link", "")
                        title = self._clean_text(entry.get("title", ""))
                        if not link or not title:
                            continue

                        body = self._extract_body(entry)
                        if not body:
                            continue

                        if keywords and not self._matches_keywords(title, body, keywords):
                            continue

                        author = label or entry.get("author", "") or feed_title or source

                        all_articles.append(ScrapedArticle(
                            title=title,
                            url=link,
                            content=body[:max_chars],
                            source=source,
                            channel_or_author=author,
                            published_at=published_at,
                            video_id=None,
                            image_url=None,
                        ))
                        found += 1

                    logger.info(f"  Found {found} recent items for [{source}]")
            except Exception as exc:
                # One feed's network hiccup (timeout, truncated response, etc.)
                # must not discard every other feed already collected this run.
                logger.error(f"Feed [{source}] {url} failed: {exc}")

            delay = feed_cfg.get("delay_after_seconds", 0)
            if delay and i < len(self.feeds) - 1:
                time.sleep(delay)

        logger.info(f"RSS feed scraper finished. Total items: {len(all_articles)}")
        return all_articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_body(entry) -> str:
        """content[0].value (Atom/full-content feeds) falls back to summary (RSS 2.0 excerpts)."""
        content = entry.get("content")
        raw = content[0].get("value", "") if content else entry.get("summary", "")
        return RssFeedScraper._clean_text(raw)

    @staticmethod
    def _clean_text(raw: str) -> str:
        text = _TAG_RE.sub(" ", raw or "")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _matches_keywords(title: str, body: str, keywords: List[str]) -> bool:
        haystack = f"{title} {body}"
        return any(
            re.search(rf"\b{re.escape(kw)}\b", haystack, re.IGNORECASE)
            for kw in keywords
        )

    @staticmethod
    def _parse_published(entry) -> Optional[datetime]:
        """published_parsed (RSS 2.0 / most Atom feeds) falls back to updated_parsed (GitHub Atom has no published)."""
        time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if not time_struct:
            return None
        return datetime(*time_struct[:6], tzinfo=timezone.utc)
