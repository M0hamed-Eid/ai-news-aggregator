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
    hours_lookback: int = 6*24
    max_transcript_chars: int = 8000

    youtube_channels: List[dict] = field(default_factory=lambda: [
        {"name": "Andrej Karpathy", "channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
        {"name": "Yannic Kilcher",  "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"},
        {"name": "AI Explained",   "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw"},
        {"name": "Nate Herk | AI Automation",    "channel_id": "UC2ojq-nuP8ceeHqiroeKhBA"},
        {"name": "Tina Huang",  "channel_id": "UC2UXDak6o7rBm23k3Vv5dww"},
        {"name": "Patrick Ellis",  "channel_id": "UCEMA_xj3YeAI7Z6jsOw3peg"},
        {"name": "Jeff Su",  "channel_id": "UCwAnu01qlnVg1Ai2AbtTMaA"},
        {"name": "Elie Steinbock",  "channel_id": "UCp48vy_SNmQ0rrqfArxnRLw"},
        {"name": "Alex Finn",  "channel_id": "UCfQNB91qRP_5ILeu_S_bSkg"},
        {"name": "Brian Casel",  "channel_id": "UCSxPE9PHHxQUEt6ajGmQyMA"},
        {"name": "Marketing Against the Grain",  "channel_id": "UCGtXqPiNV8YC0GMUzY-EUFg"},
        {"name": "Greg Isenberg",  "channel_id": "UCPjNBjflYl0-HQtUvOx0Ibw"},
        {"name": "Silicon Valley Girl",  "channel_id": "UCiq1FIgtEK7LRAOB1JXTPig"},
        {"name": "Grace Leung",  "channel_id": "UCrB7UFnkosBjAhOg3a9NdWw"},
        {"name": "Skill Leap AI",  "channel_id": "UCwSozl89jl2zUDzQ4jGJD3g"},
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