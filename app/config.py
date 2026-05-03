# app/config.py

# This file is the single source of truth for all project settings.
# Instead of hardcoding values inside scrapers or agents, we read from here.
# This makes it easy to change settings without hunting through multiple files.

from dataclasses import dataclass, field
from typing import List


@dataclass
class UserProfile:
    """
    Represents the person receiving the digest.
    Agents use this to personalize summaries and rankings.
    """
    name: str = "Mohammed"
    interests: List[str] = field(default_factory=lambda: [
        "large language models",
        "AI agents",
        "open source models",
        "NLP",
        "machine learning research",
        "RAG and vector databases",
    ])


@dataclass
class ScraperConfig:
    """
    Controls how scrapers behave.
    hours_lookback = how far back to fetch videos (24 = last 24 hours)
    max_transcript_chars = we don't need the full 2-hour transcript, just enough context
    """
    hours_lookback: int = 24
    max_transcript_chars: int = 8000

    youtube_channels: List[dict] = field(default_factory=lambda: [
        {"name": "Andrej Karpathy", "channel_id": "UCbXgNpp0jedKWcQiULLbDTA"},
        {"name": "Yannic Kilcher",  "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"},
        {"name": "AI Explained",   "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw"},
    ])


@dataclass  
class AppConfig:
    """
    Top-level config object. Import this anywhere in the project.
    Usage:  from app.config import config
    """
    user: UserProfile = field(default_factory=UserProfile)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)


# Single instance — import this everywhere
config = AppConfig()