# app/database/seed_sources.py
#
# Backfills the Source Registry (app/database/models/source.py) with the 9
# sources that used to be hardcoded in ScraperConfig (app/config.py). Idempotent
# upsert-by-key — safe to re-run any time (e.g. after adding a new source row
# here, or after editing an existing one's config).
#
# Usage:
#   python -m app.database.seed_sources

import logging

logging.basicConfig(
    level="INFO",
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# The 9 seed rows
# =============================================================================
# Each dict maps 1:1 onto Source's columns (minus id/timestamps/is_active,
# which default to True/server-generated). Deliberately does NOT include
# blog_openai/blog_anthropic — BlogScraper stays hardcoded/legacy.

SEED_SOURCES = [
    {
        "key": "arxiv",
        "name": "arXiv",
        "category": "research",
        "adapter_type": "api",
        "handler": "arxiv",
        "config": {"categories": ["cs.AI", "cs.CL", "cs.LG"]},
        "schedule_hours": 24,
    },
    {
        "key": "github_release",
        "name": "GitHub Releases",
        "category": "open_source",
        "adapter_type": "api",
        "handler": "github_release",
        "config": {
            "repos": [
                "huggingface/transformers",
                "langchain-ai/langchain",
                "vllm-project/vllm",
                "ollama/ollama",
                "run-llama/llama_index",
                "microsoft/autogen",
            ]
        },
        "schedule_hours": 24,
    },
    {
        "key": "youtube",
        "name": "YouTube",
        "category": "media",
        "adapter_type": "api",
        "handler": "youtube",
        "config": {
            "channels": [
                {"name": "Andrej Karpathy",             "channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
                {"name": "Yannic Kilcher",              "channel_id": "UCZHmQk67mSJgfCCTn7xBfew"},
                {"name": "AI Explained",                "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw"},
                {"name": "Nate Herk | AI Automation",   "channel_id": "UC2ojq-nuP8ceeHqiroeKhBA"},
                {"name": "Tina Huang",                  "channel_id": "UC2UXDak6o7rBm23k3Vv5dww"},
                {"name": "Patrick Ellis",               "channel_id": "UCEMA_xj3YeAI7Z6jsOw3peg"},
                {"name": "Jeff Su",                     "channel_id": "UCwAnu01qlnVg1Ai2AbtTMaA"},
                {"name": "Elie Steinbock",              "channel_id": "UCp48vy_SNmQ0rrqfArxnRLw"},
                {"name": "Alex Finn",                   "channel_id": "UCfQNB91qRP_5ILeu_S_bSkg"},
                {"name": "Brian Casel",                 "channel_id": "UCSxPE9PHHxQUEt6ajGmQyMA"},
                {"name": "Marketing Against the Grain", "channel_id": "UCGtXqPiNV8YC0GMUzY-EUFg"},
                {"name": "Greg Isenberg",               "channel_id": "UCPjNBjflYl0-HQtUvOx0Ibw"},
                {"name": "Silicon Valley Girl",         "channel_id": "UCiq1FIgtEK7LRAOB1JXTPig"},
                {"name": "Grace Leung",                 "channel_id": "UCrB7UFnkosBjAhOg3a9NdWw"},
                {"name": "Skill Leap AI",               "channel_id": "UCwSozl89jl2zUDzQ4jGJD3g"},
            ],
            # M7: full transcript capture — omitted (was 8000) so
            # YouTubeScraper stops truncating stored transcripts. Processing
            # long transcripts (chaptered summaries) is deferred to M12.
        },
        "schedule_hours": 24,
    },
    {
        "key": "reddit",
        "name": "Reddit",
        "category": "developer_communities",
        "adapter_type": "rss",
        "handler": None,
        "config": {
            "feeds": [
                {
                    "url": f"https://www.reddit.com/r/{sub}/.rss",
                    "source": "reddit",
                    "label": f"r/{sub}",
                    "headers": {"User-Agent": "Mozilla/5.0 (compatible; ai-news-aggregator/1.0)"},
                    # Reddit's own .rss endpoints allow ~1 request/60s per IP
                    # regardless of User-Agent — space requests out or every
                    # feed past the first gets a 429.
                    "delay_after_seconds": 65,
                }
                for sub in ["MachineLearning", "LocalLLaMA", "artificial", "singularity"]
            ]
        },
        "schedule_hours": 24,
    },
    {
        "key": "government_us",
        "name": "US Federal Register",
        "category": "government",
        "adapter_type": "api",
        "handler": "federal_register",
        "config": {"terms": ["artificial intelligence", "machine learning"]},
        "schedule_hours": 24,
    },
    {
        "key": "government_uk",
        "name": "UK Government",
        "category": "government",
        "adapter_type": "rss",
        "handler": None,
        "config": {
            "feeds": [
                {
                    "url": "https://www.gov.uk/search/all.atom?keywords=artificial+intelligence&order=relevance",
                    "source": "government_uk",
                    "label": "UK Government",
                }
            ]
        },
        "schedule_hours": 24,
    },
    {
        "key": "government_nist",
        "name": "NIST News",
        "category": "government",
        "adapter_type": "rss",
        "handler": None,
        "config": {
            "feeds": [
                {
                    "url": "https://www.nist.gov/news-events/news/rss.xml",
                    "source": "government_nist",
                    "label": "NIST",
                    "filter_keywords": ["artificial intelligence", "machine learning", "AI", "neural network"],
                }
            ]
        },
        "schedule_hours": 24,
    },
    {
        "key": "funding_crunchbase",
        "name": "Crunchbase News — AI",
        "category": "funding",
        "adapter_type": "rss",
        "handler": None,
        "config": {
            "feeds": [
                {
                    "url": "https://news.crunchbase.com/sections/ai/feed/",
                    "source": "funding_crunchbase",
                    "label": "Crunchbase News — AI",
                }
            ]
        },
        "schedule_hours": 24,
    },
    {
        "key": "huggingface_model",
        "name": "Hugging Face Models",
        "category": "product_model_databases",
        "adapter_type": "api",
        "handler": "huggingface",
        "config": {"fetch_limit": 100},
        "schedule_hours": 24,
    },
]


def seed_sources() -> None:
    """
    Upsert every row in SEED_SOURCES by key: update the existing row's fields
    if a source with that key already exists, else create a new one. Safe to
    re-run — this never duplicates rows and never touches is_active/last_run_at/
    last_success_at on existing rows (those are runtime state, not seed data).
    """
    from app.database.session import get_db_session
    from app.database.repositories.source_repository import SourceRepository
    from app.database.models.source import Source

    created, updated = 0, 0

    with get_db_session() as db:
        repo = SourceRepository(db)

        for row in SEED_SOURCES:
            existing = repo.get_by_key(row["key"])
            if existing is not None:
                existing.name = row["name"]
                existing.category = row["category"]
                existing.adapter_type = row["adapter_type"]
                existing.handler = row["handler"]
                existing.config = row["config"]
                existing.schedule_hours = row["schedule_hours"]
                logger.info(f"Updated source: {row['key']}")
                updated += 1
            else:
                db.add(Source(**row))
                logger.info(f"Created source: {row['key']}")
                created += 1

    logger.info(f"Seed complete. created={created} updated={updated} total={len(SEED_SOURCES)}")


if __name__ == "__main__":
    seed_sources()
