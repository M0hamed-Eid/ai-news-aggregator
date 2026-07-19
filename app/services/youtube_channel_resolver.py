# app/services/youtube_channel_resolver.py
#
# Resolves a user-submitted YouTube channel URL/@handle into a stable
# channel_id + display name, so a custom YouTube source can be canonicalized
# and validated through the SAME pipeline as an RSS custom source — see
# app/tasks/source_submission_tasks.py::evaluate_and_register_youtube_source_task.
#
# Uses yt-dlp (already a pinned pipeline dependency — app/services/
# stt_service.py already does an identical metadata-only, skip_download
# call for per-video duration lookups) rather than hand-written URL
# parsing: yt-dlp already normalizes every real-world channel URL shape
# (/channel/UC..., /@handle, /c/name, /user/name) into the same channel_id.

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# A YouTube channel's own "uploads" feed — the same Atom-feed URL shape
# app/scrapers/youtube_scraper.py already feedparses for the curated
# channels. Reused here as BOTH the relevance-gate input (evaluate_source()
# is unmodified — it already just wants a feedparser-able URL) and the
# canonicalization key stored in Source.feed_url (its existing unique
# constraint gives duplicate-channel dedup for free, no schema change).
CHANNEL_VIDEOS_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


@dataclass
class ResolvedChannel:
    channel_id: str
    name: str
    feed_url: str


def resolve_channel(url_or_handle: str) -> Optional[ResolvedChannel]:
    """
    Resolve any YouTube channel URL/@handle into its stable channel_id and
    display name. Returns None on any resolution failure (private/deleted/
    invalid channel, network error, or a URL that isn't a channel at all)
    — callers surface a friendly message, not a stack trace.
    """
    import yt_dlp

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_or_handle, download=False)
    except Exception:
        logger.warning("youtube_channel_resolver: failed to resolve %r", url_or_handle, exc_info=True)
        return None

    channel_id = info.get("channel_id") or info.get("id")
    name = info.get("channel") or info.get("uploader") or channel_id

    if not channel_id or not str(channel_id).startswith("UC"):
        logger.warning(
            "youtube_channel_resolver: no valid channel_id resolved for %r (got %r)", url_or_handle, channel_id
        )
        return None

    return ResolvedChannel(
        channel_id=channel_id,
        name=name,
        feed_url=CHANNEL_VIDEOS_FEED_URL.format(channel_id=channel_id),
    )
