# app/scrapers/youtube_scraper.py

import feedparser                          # parses RSS/Atom XML feeds
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,                   # raised when a video has no captions
    NoTranscriptFound,                     # raised when no usable transcript exists
)
from datetime import datetime, timezone
from typing import List
import logging

from app.scrapers.base_scraper import BaseScraper, ScrapedArticle
from app.config import config

# logging = a professional alternative to print()
# Instead of print("fetching...") we use logger.info("fetching...")
# This lets us control log levels (DEBUG / INFO / WARNING / ERROR) and
# later write logs to files instead of just the terminal.
logger = logging.getLogger(__name__)


class YouTubeScraper(BaseScraper):
    """
    Scrapes latest videos from YouTube channels using RSS feeds,
    then fetches the transcript for each recent video.
    """

    # YouTube exposes an RSS feed for every channel at this URL pattern.
    # We just swap in the channel_id and get back XML with the latest 15 videos.
    RSS_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    def __init__(self):
        # Call the parent class constructor with our source name
        super().__init__(source_name="youtube")

        # Read channel list from config — no hardcoding inside the scraper
        self.channels = config.scraper.youtube_channels

        # How many characters of transcript to keep
        # A full 1-hour video transcript can be 50,000+ characters — we don't need all of it
        self.max_transcript_chars = config.scraper.max_transcript_chars

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        """
        Main method. Loops through all configured channels,
        fetches recent videos, and retrieves their transcripts.
        Returns a flat list of ScrapedArticle objects.
        """
        all_articles = []

        for channel in self.channels:
            logger.info(f"Scraping channel: {channel['name']}")

            # Get recent videos from this channel's RSS feed
            videos = self._fetch_recent_videos(
                channel_id=channel["channel_id"],
                channel_name=channel["name"],
                hours_lookback=hours_lookback,
            )

            logger.info(f"  Found {len(videos)} recent videos")

            # For each video, try to get its transcript
            for video in videos:
                transcript = self._fetch_transcript(video["video_id"])

                # If we got a transcript, create a ScrapedArticle
                if transcript:
                    article = ScrapedArticle(
                        title=video["title"],
                        url=video["url"],
                        content=transcript,
                        source=self.source_name,
                        channel_or_author=channel["name"],
                        published_at=video["published_at"],
                        video_id=video["video_id"],
                    )
                    all_articles.append(article)
                else:
                    logger.warning(f"  No transcript for: {video['title']}")

        logger.info(f"YouTube scraper finished. Total articles: {len(all_articles)}")
        return all_articles

    def _fetch_recent_videos(
        self, channel_id: str, channel_name: str, hours_lookback: int
    ) -> List[dict]:
        """
        Fetches the RSS feed for a channel and filters for recent videos.

        feedparser.parse() downloads the RSS XML and converts it into
        a Python object where feed.entries is a list of video items.
        Each entry has: title, link, published_parsed (a time.struct_time tuple)
        """
        feed_url = self.RSS_FEED_URL.format(channel_id=channel_id)
        feed = feedparser.parse(feed_url)

        # feedparser returns an empty entries list (not an error) if something went wrong.
        # We check explicitly so we can log a useful message.
        if not feed.entries:
            logger.warning(f"No entries found for channel {channel_name}. "
                           f"The channel ID may be wrong or the feed is empty.")
            return []

        recent_videos = []

        for entry in feed.entries:
            # entry.published_parsed is a time.struct_time (a tuple of time components)
            # datetime(*...) unpacks it into a proper datetime object
            # [:6] takes only (year, month, day, hour, minute, second) — ignoring weekday etc.
            published_at = datetime(
                *entry.published_parsed[:6], tzinfo=timezone.utc
            )

            # Use the base class helper to check if this video is recent enough
            if not self._is_recent(published_at, hours_lookback):
                continue  # skip videos older than our lookback window

            # entry.yt_videoid is a special field feedparser extracts from YouTube RSS
            # It's the unique ID at the end of every YouTube URL: youtube.com/watch?v=VIDEO_ID
            video_id = entry.get("yt_videoid", "")

            if not video_id:
                logger.warning(f"Could not extract video ID from entry: {entry.title}")
                continue

            recent_videos.append({
                "title": entry.title,
                "url": entry.link,
                "video_id": video_id,
                "published_at": published_at,
            })

        return recent_videos

    def _fetch_transcript(self, video_id: str) -> str:
        """
        Fetches the transcript for a single YouTube video.

        YouTubeTranscriptApi returns a list of dicts like:
        [{"text": "hello world", "start": 0.5, "duration": 1.2}, ...]

        We join all "text" values into one string — we don't care about timestamps,
        only the spoken content.
        """
        try:
            # list() returns available transcript options for the video
            # Some videos have manual captions, some have auto-generated ones,
            # some have both. We want to find a usable English one.
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.list(video_id)

            # Try to find a manually-created English transcript first (higher quality)
            # If not found, fall back to auto-generated English
            # If no English at all, try any auto-generated language and translate
            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except NoTranscriptFound:
                    # Last resort: get whatever language exists and translate it
                    transcript = transcript_list.find_generated_transcript(
                        transcript_list._generated_transcripts.keys()
                    ).translate("en")

            # fetch() downloads the actual transcript data
            # Each item is {"text": "...", "start": float, "duration": float}
            raw_data = transcript.fetch()

            # Join all text segments into one clean string
            # .strip() removes leading/trailing whitespace from each segment
            full_text = " ".join(
                segment.text.strip() for segment in raw_data
            )

            # Truncate to our max length to avoid sending huge prompts to the LLM later
            # We add a note at the end so the agent knows the text was cut
            if len(full_text) > self.max_transcript_chars:
                full_text = full_text[:self.max_transcript_chars] + "... [transcript truncated]"

            return full_text

        except TranscriptsDisabled:
            # The video owner has disabled captions entirely
            logger.warning(f"Transcripts disabled for video: {video_id}")
            return ""

        except NoTranscriptFound:
            # No transcript in any language
            logger.warning(f"No transcript found for video: {video_id}")
            return ""

        except Exception as e:
            # Catch-all for unexpected errors (network issues, API changes, etc.)
            # We log the error but don't crash the whole scraper
            logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
            return ""