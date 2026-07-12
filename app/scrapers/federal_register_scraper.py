# app/scrapers/federal_register_scraper.py
#
# US Federal Register — AI-related rules/notices via their official JSON API
# (federalregister.gov/api/v1). Their own search.rss endpoint is blocked by a
# bot-detection wall — confirmed live: it redirects to a captcha "request
# access" page for scripted clients regardless of query params — so this
# falls back to the documented JSON API instead, per the RSS > API priority
# (RSS was tried first and ruled out, not skipped).
#
# Output maps directly onto the existing Article table:
#   title              -> document title
#   url                -> html_url (canonical, stable)
#   content             -> abstract
#   channel_or_author  -> issuing agency name(s)
#   source             -> "government_us"

import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

from app.config import config
from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

FEDERAL_REGISTER_API_URL = "https://www.federalregister.gov/api/v1/articles.json"
MAX_ABSTRACT_CHARS = 8000


class FederalRegisterScraper(BaseScraper):

    def __init__(self):
        super().__init__(source_name="government_us")
        self.terms = config.scraper.federal_register_terms

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles: List[ScrapedArticle] = []

        for term in self.terms:
            logger.info(f"Scraping Federal Register for term: {term!r}")
            try:
                response = requests.get(
                    FEDERAL_REGISTER_API_URL,
                    params={
                        "conditions[term]": term,
                        "order": "newest",
                        "per_page": 20,
                    },
                    timeout=15,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.error(f"Federal Register request failed for {term!r}: {exc}")
                continue

            found = 0
            for item in data.get("results", []):
                published_at = self._parse_published(item.get("publication_date"))
                if published_at is None or not self._is_recent(published_at, hours_lookback):
                    continue

                url = item.get("html_url", "")
                title = (item.get("title") or "").strip()
                abstract = (item.get("abstract") or "").strip()
                if not url or not title or not abstract:
                    continue

                agencies = ", ".join(
                    agency.get("name", "") for agency in item.get("agencies", []) if agency.get("name")
                )

                all_articles.append(ScrapedArticle(
                    title=title,
                    url=url,
                    content=abstract[:MAX_ABSTRACT_CHARS],
                    source="government_us",
                    channel_or_author=agencies or "U.S. Federal Register",
                    published_at=published_at,
                    video_id=None,
                    image_url=None,
                ))
                found += 1

            logger.info(f"  Found {found} recent documents for term {term!r}")

        logger.info(f"Federal Register scraper finished. Total documents: {len(all_articles)}")
        return all_articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_published(date_str: Optional[str]) -> Optional[datetime]:
        """publication_date is date-only (YYYY-MM-DD), no time component."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
