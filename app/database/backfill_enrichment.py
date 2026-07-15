# app/database/backfill_enrichment.py
#
# Deliberate, versioned corpus backfill of enrichment (M8) — NOT scheduled,
# NOT run automatically by the normal pipeline. Runs EnrichmentAgent over the
# pre-M8 corpus (everything with no content_enrichment row yet) via Ollama's
# local model by default, to avoid Groq bulk-call cost (per docs/ROADMAP.md:
# "run on Ollama local fallback to avoid Groq bulk cost"). Every row this
# script writes is tagged with a DISTINCT enrichment_version (default
# "v1-backfill-ollama") so it's always identifiable in the data as a backfill
# pass, separate from live-ingest rows tagged with EnrichmentAgent's own
# ENRICHMENT_VERSION.
#
# Usage:
#   python -m app.database.backfill_enrichment --limit 20        # small test batch first
#   python -m app.database.backfill_enrichment                   # full corpus (no limit) — SLOW, run deliberately
#   python -m app.database.backfill_enrichment --provider groq   # override if you'd rather pay for Groq bulk cost
#
# The --limit flag is a per-call cap on EACH of articles/videos (matches
# DigestService._enrich_unenriched()'s own batch_limit semantics) — re-run
# repeatedly with the same --limit to work through the corpus incrementally
# and inspect quality between batches, rather than committing to the full
# run blind.

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_BACKFILL_VERSION = "v1-backfill-ollama"


def backfill_enrichment(limit: int | None, provider: str, version: str) -> None:
    # Force the provider for this process only — never mutates the user's
    # real .env, just this script's own os.environ for its lifetime.
    os.environ["LLM_PROVIDER"] = provider

    from app.config import AppConfig
    from app.services.digest_service import DigestService

    logger.info(
        "Backfill starting: provider=%s enrichment_version=%s limit=%s",
        provider, version, limit if limit is not None else "ALL (no limit — full corpus)",
    )

    svc = DigestService(config=AppConfig(), enrichment_version=version)
    art_count, vid_count, errors = svc._enrich_unenriched(limit=limit)

    logger.info(
        "Backfill batch complete: articles=%d videos=%d errors=%d",
        art_count, vid_count, len(errors),
    )
    for err in errors:
        logger.warning("  Backfill error: %s", err)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M8 deliberate, versioned corpus enrichment backfill")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max articles AND max videos to enrich in this call (default: no limit — full remaining corpus)",
    )
    parser.add_argument(
        "--provider", choices=["local", "groq"], default="local",
        help="'local' (Ollama, default — avoids Groq bulk cost) or 'groq'",
    )
    parser.add_argument(
        "--version", default=DEFAULT_BACKFILL_VERSION,
        help=f"enrichment_version tag for every row this run writes (default: {DEFAULT_BACKFILL_VERSION!r})",
    )
    args = parser.parse_args()

    if args.provider == "groq" and not os.getenv("GROQ_API_KEY"):
        print("Error: --provider groq requires GROQ_API_KEY to be set.", file=sys.stderr)
        sys.exit(1)

    backfill_enrichment(limit=args.limit, provider=args.provider, version=args.version)
