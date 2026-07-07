# app/config.py
#
# Single source of truth for all project settings.
#
# Changes from original
# ---------------------
# 1. Added UserProfile.expertise_level and UserProfile.preferences so the
#    curator agent has richer context to rank content — these fields were
#    referenced in the original curator_agent.py but missing from config.
# 2. Added UserProfile.email so DigestService knows where to send the digest
#    without hard-coding an address in run_pipeline.py.
# 3. No breaking changes to existing fields.

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class UserProfile:
    """
    Represents the person receiving the digest.
    Agents use this to personalise summaries and rankings.
    """
    name: str = "Mohammed"

    # Email address the digest is sent to
    email: str = ""  # set via RECIPIENT_EMAIL env var in AppConfig.__post_init__

    interests: List[str] = field(default_factory=lambda: [
        "large language models",
        "AI agents",
        "open source models",
        "NLP",
        "machine learning research",
        "RAG and vector databases",
    ])

    # Used by CuratorAgent when building the system prompt
    expertise_level: str = "advanced"  # beginner | intermediate | advanced

    preferences: Dict[str, str] = field(default_factory=lambda: {
        "content_depth": "technical",       # technical | overview
        "preferred_sources": "all",         # all | youtube | blogs
        "max_video_length": "any",          # any | short | medium
    })


@dataclass
class ScraperConfig:
    """
    Controls how scrapers behave.
    hours_lookback = how far back to fetch videos (24 = last 24 hours).
    max_transcript_chars = we don't need the full 2-hour transcript.
    """
    hours_lookback: int = 6 * 24
    max_transcript_chars: int = 8_000

    youtube_channels: List[dict] = field(default_factory=lambda: [
        {"name": "Andrej Karpathy",            "channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
        {"name": "Yannic Kilcher",             "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"},
        {"name": "AI Explained",               "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw"},
        {"name": "Nate Herk | AI Automation",  "channel_id": "UC2ojq-nuP8ceeHqiroeKhBA"},
        {"name": "Tina Huang",                 "channel_id": "UC2UXDak6o7rBm23k3Vv5dww"},
        {"name": "Patrick Ellis",              "channel_id": "UCEMA_xj3YeAI7Z6jsOw3peg"},
        {"name": "Jeff Su",                    "channel_id": "UCwAnu01qlnVg1Ai2AbtTMaA"},
        {"name": "Elie Steinbock",             "channel_id": "UCp48vy_SNmQ0rrqfArxnRLw"},
        {"name": "Alex Finn",                  "channel_id": "UCfQNB91qRP_5ILeu_S_bSkg"},
        {"name": "Brian Casel",                "channel_id": "UCSxPE9PHHxQUEt6ajGmQyMA"},
        {"name": "Marketing Against the Grain","channel_id": "UCGtXqPiNV8YC0GMUzY-EUFg"},
        {"name": "Greg Isenberg",              "channel_id": "UCPjNBjflYl0-HQtUvOx0Ibw"},
        {"name": "Silicon Valley Girl",        "channel_id": "UCiq1FIgtEK7LRAOB1JXTPig"},
        {"name": "Grace Leung",                "channel_id": "UCrB7UFnkosBjAhOg3a9NdWw"},
        {"name": "Skill Leap AI",              "channel_id": "UCwSozl89jl2zUDzQ4jGJD3g"},
    ])



@dataclass
class ScraperConfig:
    hours_lookback: int = 24
    max_transcript_chars: int = 8_000

    youtube_channels: List[dict] = field(default_factory=lambda: [
        # ... unchanged ...
    ])

    # NEW — arXiv subject categories to poll for new papers.
    # Full category list: https://arxiv.org/category_taxonomy
    arxiv_categories: List[str] = field(default_factory=lambda: [
        "cs.AI",   # Artificial Intelligence
        "cs.CL",   # Computation and Language (NLP)
        "cs.LG",   # Machine Learning
    ])

@dataclass
class AppConfig:
    """
    Top-level config object. Import this anywhere in the project.

    Usage:
        from app.config import config
    """
    user: UserProfile = field(default_factory=UserProfile)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)

    def __post_init__(self) -> None:
        import os
        # Allow the recipient email to be overridden via environment variable
        # without requiring code changes.
        env_email = os.getenv("RECIPIENT_EMAIL", "")
        if env_email:
            self.user.email = env_email


# Single instance — import this everywhere
config = AppConfig()