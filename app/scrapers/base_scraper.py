# app/scrapers/base_scraper.py

# Why a base class?
# Both YouTube and blog scrapers share common behavior:
# - they return the same data shape (title, url, content, published_at, source)
# - they both need a "scrape" method
# Instead of copying that structure into every scraper, we define it once here.
# Each child scraper just implements the scrape() method differently.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ScrapedArticle:
    """
    A single piece of content returned by any scraper.
    Every scraper — YouTube, OpenAI blog, Anthropic blog — returns a list of these.
    Using one shared shape means the database layer doesn't care which scraper produced the data.
    """
    title: str
    url: str
    content: str                    # transcript for YouTube, article text for blogs
    source: str                     # e.g. "youtube", "openai_blog"
    channel_or_author: str          # e.g. "Andrej Karpathy"
    published_at: datetime
    video_id: Optional[str] = None  # only relevant for YouTube videos


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.
    ABC = Abstract Base Class. It means this class can't be used directly —
    you must create a child class that implements the scrape() method.
    This enforces a contract: every scraper MUST have a scrape() method.
    """

    def __init__(self, source_name: str):
        # Every scraper knows its own name (used for logging and the ScrapedArticle)
        self.source_name = source_name

    @abstractmethod
    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        """
        Must be implemented by every child scraper.
        Returns a list of ScrapedArticle objects from the last `hours_lookback` hours.
        """
        pass

    def _is_recent(self, published_at: datetime, hours_lookback: int) -> bool:
        """
        Helper method: checks if a datetime falls within our lookback window.
        Both scrapers use this check, so it lives here in the base class.

        datetime.utcnow() gives us the current time in UTC.
        We subtract the article's publish time to get the age.
        total_seconds() / 3600 converts seconds to hours.
        """
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # Make published_at timezone-aware if it isn't already
        # RSS feeds sometimes return naive datetimes (no timezone info)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        age_in_hours = (now - published_at).total_seconds() / 3600
        return age_in_hours <= hours_lookback