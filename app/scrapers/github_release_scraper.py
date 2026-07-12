# app/scrapers/github_release_scraper.py
#
# Scrapes new releases from a configured list of GitHub repos via their
# public per-repo Atom feeds (https://github.com/{owner}/{repo}/releases.atom)
# — no API key, no REST rate limits, no scraping. Same "just parse the feed"
# pattern already used for arXiv (arxiv_scraper.py) and OpenAI's blog.
#
# This is our first "Open Source" category source: release notes for major
# AI/ML libraries are high-signal AI news (new model support, breaking
# changes, major features) and map directly onto the existing Article table.
#
# Output maps directly onto the existing Article table:
#   title              -> "{owner}/{repo} {release tag/name}"
#   url                -> the release's GitHub page (canonical, stable)
#   content             -> release notes body (already good digest-agent input)
#   channel_or_author  -> "{owner}/{repo}"
#   source             -> "github_release"

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

import feedparser

from app.config import config
from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

GITHUB_RELEASES_ATOM_URL = "https://github.com/{repo}/releases.atom"
MAX_RELEASE_NOTES_CHARS = 8000  # consistent with MAX_ABSTRACT_CHARS in arxiv_scraper.py

_TAG_RE = re.compile(r"<[^>]+>")


class GitHubReleaseScraper(BaseScraper):

    def __init__(self):
        super().__init__(source_name="github_release")
        self.repos = config.scraper.github_repos

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles: List[ScrapedArticle] = []

        for repo in self.repos:
            logger.info(f"Scraping GitHub releases for: {repo}")
            feed_url = GITHUB_RELEASES_ATOM_URL.format(repo=repo)
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                logger.warning(f"No release entries for {repo}")
                continue

            found = 0
            for entry in feed.entries:
                published_at = self._parse_published(entry)
                if published_at is None or not self._is_recent(published_at, hours_lookback):
                    continue

                url = entry.get("link", "")
                release_name = self._clean_title(entry.get("title", ""))
                if not url or not release_name:
                    continue

                notes = self._clean_notes(entry.get("content", [{}])[0].get("value", "") or entry.get("summary", ""))
                if not notes:
                    continue

                all_articles.append(ScrapedArticle(
                    title=f"{repo} {release_name}",
                    url=url,
                    content=notes[:MAX_RELEASE_NOTES_CHARS],
                    source="github_release",
                    channel_or_author=repo,
                    published_at=published_at,
                    video_id=None,
                    image_url=None,
                ))
                found += 1

            logger.info(f"  Found {found} recent releases for {repo}")

        logger.info(f"GitHub release scraper finished. Total releases: {len(all_articles)}")
        return all_articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_title(raw_title: str) -> str:
        """Atom entry titles are just the release tag/name, e.g. 'v4.46.0' — used as-is."""
        return (raw_title or "").strip()

    @staticmethod
    def _clean_notes(raw_notes: str) -> str:
        """Release notes come through as HTML (GitHub renders the Markdown body) — strip tags."""
        text = _TAG_RE.sub(" ", raw_notes or "")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_published(entry) -> Optional[datetime]:
        time_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if not time_struct:
            return None
        return datetime(*time_struct[:6], tzinfo=timezone.utc)
