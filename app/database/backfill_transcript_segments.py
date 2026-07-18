# app/database/backfill_transcript_segments.py
#
# M12 one-time-per-row backfill: re-fetches per-segment transcript timing for
# videos scraped before the segment-capture fix landed
# (app/scrapers/youtube_scraper.py::_fetch_transcript now returns segments;
# previously it discarded them, storing only flat text). Every existing row
# already has real content — caption-less videos were dropped entirely before
# M12, never stored empty — so this backfill only ever ADDS
# transcript_segments/duration_seconds, it never touches `content`.
#
# Uses YouTubeTranscriptApi directly (via a channel-less YouTubeScraper
# instance, reusing its _fetch_transcript/_sleep) rather than yt-dlp — no
# audio download needed, captions are still fetchable for these videos by
# definition (they're in the DB because captions worked the first time).
#
# Usage:
#   python -m app.database.backfill_transcript_segments --limit 10   # small test batch first
#   python -m app.database.backfill_transcript_segments              # full corpus (no limit) — SLOW, run deliberately

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def backfill_transcript_segments(limit: int | None) -> None:
    from app.database.session import get_db_session
    from app.database.repositories.youtube_repository import YoutubeRepository, _derive_duration_seconds
    from app.scrapers.youtube_scraper import YouTubeScraper

    scraper = YouTubeScraper(channels=[])  # channels unused by _fetch_transcript/_sleep

    batch_limit = limit if limit is not None else 10_000
    updated, failed = 0, 0

    with get_db_session() as db:
        repo = YoutubeRepository(db)
        videos = repo.get_missing_transcript_segments(limit=batch_limit)
        logger.info("Backfill starting: %d videos missing transcript_segments", len(videos))

        for video in videos:
            scraper._sleep()  # same polite pacing as live scraping
            _full_text, segments = scraper._fetch_transcript(video.video_id)

            if not segments:
                logger.warning("  No segments re-fetched for video_id=%s (%s) — skipping", video.video_id, video.title[:60])
                failed += 1
                continue

            video.transcript_segments = segments
            video.duration_seconds = _derive_duration_seconds(segments)
            updated += 1
            logger.info("  Backfilled video_id=%s duration=%ss segments=%d", video.video_id, video.duration_seconds, len(segments))

    logger.info("Backfill batch complete: updated=%d failed=%d", updated, failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M12 backfill of per-segment transcript timing for pre-M12 videos")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max videos to backfill in this call (default: no limit — full remaining corpus)",
    )
    args = parser.parse_args()

    backfill_transcript_segments(limit=args.limit)
