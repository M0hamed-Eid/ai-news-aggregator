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
# 4. Fixed a duplicate ScraperConfig class definition — the second (winning)
#    copy had a stub `youtube_channels` list (just a comment, no entries),
#    silently zeroing out YouTube ingestion. Merged into one class carrying
#    the real channel list + arxiv_categories, and added github_repos.
# 5. Added reddit_feeds / government_feeds / funding_feeds (each a list of
#    plain feed-definition dicts consumed by the generic RssFeedScraper —
#    see app/scrapers/rss_feed_scraper.py) plus federal_register_terms and
#    huggingface_fetch_limit for the two API-based adapters. Adding another
#    pure-RSS source later is just another dict in the relevant list here —
#    no new scraper code required.

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
    hours_lookback: int = 24
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

    # arXiv subject categories to poll for new papers.
    # Full category list: https://arxiv.org/category_taxonomy
    arxiv_categories: List[str] = field(default_factory=lambda: [
        "cs.AI",   # Artificial Intelligence
        "cs.CL",   # Computation and Language (NLP)
        "cs.LG",   # Machine Learning
    ])

    # NEW — GitHub repos to poll for new releases (owner/repo). Each maps to
    # that repo's public Atom feed: github.com/{owner}/{repo}/releases.atom
    github_repos: List[str] = field(default_factory=lambda: [
        "huggingface/transformers",
        "langchain-ai/langchain",
        "vllm-project/vllm",
        "ollama/ollama",
        "run-llama/llama_index",
        "microsoft/autogen",
    ])

    # NEW — feed definitions consumed by the generic RssFeedScraper
    # (app/scrapers/rss_feed_scraper.py). Each dict:
    #   url (required), source (required, -> Article.source),
    #   label (optional, -> channel_or_author), headers (optional dict),
    #   delay_after_seconds (optional, rate-limit friendliness),
    #   filter_keywords (optional list — word-boundary, case-insensitive
    #   match against title+body; use when the feed itself has no working
    #   topic filter), max_content_chars (optional, default 8000).
    # Adding another pure-RSS/Atom source later = one more dict here, no code.
    reddit_feeds: List[dict] = field(default_factory=lambda: [
        {
            "url": f"https://www.reddit.com/r/{sub}/.rss",
            "source": "reddit",
            "label": f"r/{sub}",
            "headers": {"User-Agent": "Mozilla/5.0 (compatible; ai-news-aggregator/1.0)"},
            # Reddit's own .rss endpoints allow ~1 request/60s per IP regardless
            # of User-Agent (confirmed via live rate-limit headers) — space
            # requests out or every feed past the first gets a 429.
            "delay_after_seconds": 65,
        }
        for sub in ["MachineLearning", "LocalLLaMA", "artificial", "singularity"]
    ])

    government_feeds: List[dict] = field(default_factory=lambda: [
        {
            # gov.uk's per-finder keyword param (news-and-communications,
            # policy-papers-and-consultations) does NOT actually filter —
            # confirmed live it just returns the whole unfiltered finder.
            # /search/all.atom with order=relevance genuinely filters.
            "url": "https://www.gov.uk/search/all.atom?keywords=artificial+intelligence&order=relevance",
            "source": "government_uk",
            "label": "UK Government",
        },
        {
            # NIST has no topic/search param on its RSS feed — it's their
            # general newsroom — so filter client-side for AI relevance.
            "url": "https://www.nist.gov/news-events/news/rss.xml",
            "source": "government_nist",
            "label": "NIST",
            "filter_keywords": ["artificial intelligence", "machine learning", "AI", "neural network"],
        },
    ])

    # US Federal Register's own search.rss is blocked by a bot-detection
    # wall (redirects to a captcha page for scripted clients) — confirmed
    # live — so it's handled by FederalRegisterScraper via their JSON API
    # instead of the generic RSS adapter. These are the search terms used.
    federal_register_terms: List[str] = field(default_factory=lambda: [
        "artificial intelligence",
        "machine learning",
    ])

    funding_feeds: List[dict] = field(default_factory=lambda: [
        {
            # Crunchbase News' AI section — every sampled entry is an actual
            # funding round / investor-market story (confirmed live), unlike
            # TechCrunch/VentureBeat's AI feeds which mix in general product
            # news. Swappable later — just replace/add entries in this list.
            "url": "https://news.crunchbase.com/sections/ai/feed/",
            "source": "funding_crunchbase",
            "label": "Crunchbase News — AI",
        },
    ])

    # How many of Hugging Face's newest models to fetch per run before
    # filtering — sort=createdAt is a firehose of low-effort test uploads
    # (confirmed live: brand-new models with zero likes/downloads and no
    # library tag), so HuggingFaceScraper over-fetches and then keeps only
    # models with a recognized library_name.
    huggingface_fetch_limit: int = 100

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