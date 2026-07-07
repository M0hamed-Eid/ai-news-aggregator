# app/scrapers/arxiv_scraper.py
#
# Scrapes newly-announced papers from arXiv via their official per-category
# RSS feeds (https://rss.arxiv.org/rss/{category}) — no API key, no scraping,
# no Playwright. This is the same "just parse the feed" pattern already used
# for OpenAI's blog in blog_scraper.py.
#
# Output maps directly onto the existing Article table:
#   title              -> paper title
#   url                -> arXiv abstract page (canonical, stable)
#   content             -> paper abstract (already a good digest-agent input,
#                          no need to fetch/render the full PDF)
#   channel_or_author  -> author list as a single string
#   source             -> "arxiv"

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import feedparser

from app.config import config
from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

ARXIV_RSS_URL = "https://rss.arxiv.org/rss/{category}"
MAX_ABSTRACT_CHARS = 8000  # consistent with MAX_ARTICLE_CHARS in blog_scraper.py

_TAG_RE = re.compile(r"<[^>]+>")
_ARXIV_ID_SUFFIX_RE = re.compile(r"\s*\(arXiv:\S+\)\s*$")


class ArxivScraper(BaseScraper):

    def __init__(self):
        super().__init__(source_name="arxiv")
        self.categories = config.scraper.arxiv_categories

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles: List[ScrapedArticle] = []

        for category in self.categories:
            logger.info(f"Scraping arXiv category: {category}")
            feed_url = ARXIV_RSS_URL.format(category=category)
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                logger.warning(f"No entries for arXiv category {category}")
                continue

            found = 0
            for entry in feed.entries:
                published_at = self._parse_published(entry)
                if published_at is None or not self._is_recent(published_at, hours_lookback):
                    continue

                url = entry.get("link", "")
                title = self._clean_title(entry.get("title", ""))
                if not url or not title:
                    continue

                abstract = self._clean_abstract(entry.get("summary", ""))
                if not abstract:
                    continue

                all_articles.append(ScrapedArticle(
                    title=title,
                    url=url,
                    content=abstract[:MAX_ABSTRACT_CHARS],
                    source="arxiv",
                    channel_or_author=self._truncate_authors(entry.get("author", "")),
                    published_at=published_at,
                    video_id=None,
                    image_url=None,
                ))
                found += 1

            logger.info(f"  Found {found} recent papers in {category}")

        logger.info(f"arXiv scraper finished. Total papers: {len(all_articles)}")
        return all_articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_title(raw_title: str) -> str:
        """arXiv RSS titles sometimes end with '(arXiv:2401.12345v1 [cs.AI])' — strip it."""
        return _ARXIV_ID_SUFFIX_RE.sub("", raw_title).strip()

    @staticmethod
    def _clean_abstract(raw_summary: str) -> str:
        """The feed wraps the abstract in HTML with an 'Abstract:' prefix — strip both."""
        text = _TAG_RE.sub(" ", raw_summary or "")
        text = re.sub(r"^\s*Abstract:\s*", "", text.strip(), flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_published(entry) -> Optional[datetime]:
        time_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if not time_struct:
            return None
        return datetime(*time_struct[:6], tzinfo=timezone.utc)
    
    @staticmethod
    def _truncate_authors(raw_authors: str, max_len: int = 197) -> str:
        """
        Article.author is String(200) in the DB. arXiv papers can have 15+
        co-authors, easily exceeding that — truncate here so one long-author
        paper can't poison the whole bulk insert (ON CONFLICT DO NOTHING still
        fails the ENTIRE batch if any single row violates a column constraint).
        """
        raw_authors = raw_authors.strip() or "arXiv"
        if len(raw_authors) <= max_len:
            return raw_authors
        return raw_authors[:max_len].rsplit(",", 1)[0] + " et al."