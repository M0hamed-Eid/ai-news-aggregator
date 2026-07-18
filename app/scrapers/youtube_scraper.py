# app/scrapers/youtube_scraper.py

import feedparser
import logging
import os
import time
import random
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from datetime import datetime, timezone
from typing import List
 
from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)
 
# Random delay between transcript fetches — avoids YouTube rate limiting
MIN_DELAY = 5
MAX_DELAY = 12
 
# Residential proxy URL from .env
# Format: http://user:pass@host:port  OR  http://host:port
PROXY_URL = os.getenv("RESIDENTIAL_PROXY_URL", "")
 
 
class YouTubeScraper(BaseScraper):
 
    RSS_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
 
    def __init__(self, channels: List[dict], max_transcript_chars: int | None = None):
        super().__init__(source_name="youtube")
        self.channels = channels
        # M7: full transcript capture — None (the default) means NO truncation.
        # Consumers that need a bounded length (LLM prompts, embeddings) already
        # cap their own input independently at the point of use (see
        # app/agents/digest_agent.py, run_pipeline.py's run_embedding_phase) —
        # this cap only ever affected what got STORED in Postgres.
        self.max_transcript_chars = max_transcript_chars
 
        # Build the YouTubeTranscriptApi instance with proxy if configured.
        # The correct API (v1.2.x) is:
        #   YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=..., https_url=...))
        # NOT:  ytt_api.list(proxies=...)  ← this is wrong and causes the crash we saw
        if PROXY_URL:
            try:
                from youtube_transcript_api.proxies import GenericProxyConfig
                self._ytt_api = YouTubeTranscriptApi(
                    proxy_config=GenericProxyConfig(
                        http_url=PROXY_URL,
                        https_url=PROXY_URL,
                    )
                )
                logger.info(f"YouTube scraper: proxy enabled ({PROXY_URL})")
            except Exception as e:
                logger.warning(f"YouTube scraper: failed to set proxy ({e}), running without proxy")
                self._ytt_api = YouTubeTranscriptApi()
        else:
            self._ytt_api = YouTubeTranscriptApi()
            logger.info(
                "YouTube scraper: no proxy — if transcripts are blocked, "
                "set RESIDENTIAL_PROXY_URL in .env"
            )
 
    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles = []

        for channel in self.channels:
            logger.info(f"Scraping channel: {channel['name']}")
            videos = self._fetch_recent_videos(
                channel_id=channel["channel_id"],
                channel_name=channel["name"],
                hours_lookback=hours_lookback,
            )
            logger.info(f"  Found {len(videos)} recent videos")

            for video in videos:
                self._sleep()  # polite delay before each transcript request
                transcript, segments = self._fetch_transcript(video["video_id"])

                # M12: a video whose captions are disabled/unavailable is no
                # longer dropped — it's inserted as a content-less stub so the
                # STT fallback chain (app/tasks/stt_tasks.py) has a row to
                # attach a transcript to later. See YoutubeRepository.bulk_create
                # for the stt_jobs bookkeeping this triggers.
                all_articles.append(ScrapedArticle(
                    title=video["title"],
                    url=video["url"],
                    content=transcript,
                    source=self.source_name,
                    channel_or_author=channel["name"],
                    published_at=video["published_at"],
                    video_id=video["video_id"],
                    channel_id=channel["channel_id"],
                    transcript_segments=segments or None,
                ))
                if not transcript:
                    logger.warning(f"  No transcript for: {video['title']} — queuing for STT")

        logger.info(f"YouTube scraper finished. Total articles: {len(all_articles)}")
        return all_articles
 
    def _fetch_recent_videos(
        self, channel_id: str, channel_name: str, hours_lookback: int
    ) -> List[dict]:
        feed_url = self.RSS_FEED_URL.format(channel_id=channel_id)
        feed = feedparser.parse(feed_url)
 
        if not feed.entries:
            logger.warning(f"No entries for channel {channel_name}. Channel ID may be wrong.")
            return []
 
        recent_videos = []
        for entry in feed.entries:
            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if not self._is_recent(published_at, hours_lookback):
                continue
 
            video_id = entry.get("yt_videoid", "")
            if not video_id:
                logger.warning(f"No video ID in entry: {entry.title}")
                continue
 
            recent_videos.append({
                "title": entry.title,
                "url": entry.link,
                "video_id": video_id,
                "published_at": published_at,
            })
 
        return recent_videos
 
    def _fetch_transcript(self, video_id: str) -> tuple[str, list]:
        """
        Returns (full_text, segments). segments is
        [{"start": float, "duration": float, "text": str}, ...] — the same
        shape STT (app/services/stt_service.py, M12) produces, so downstream
        code (chunking, duration derivation) doesn't care which path a video's
        transcript came from. On any failure both are empty — the caller
        treats that as "captions unavailable, queue for STT".
        """
        try:
            # Use self._ytt_api which was already created with the proxy in __init__
            transcript_list = self._ytt_api.list(video_id)

            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except NoTranscriptFound:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except NoTranscriptFound:
                    transcript = transcript_list.find_generated_transcript(
                        transcript_list._generated_transcripts.keys()
                    ).translate("en")

            raw_data = transcript.fetch()
            segments = [
                {"start": seg.start, "duration": seg.duration, "text": seg.text.strip()}
                for seg in raw_data
            ]
            full_text = " ".join(seg["text"] for seg in segments)

            if self.max_transcript_chars and len(full_text) > self.max_transcript_chars:
                full_text = full_text[:self.max_transcript_chars] + "... [transcript truncated]"

            return full_text, segments

        except TranscriptsDisabled:
            logger.warning(f"Transcripts disabled for video: {video_id}")
        except NoTranscriptFound:
            logger.warning(f"No transcript found for video: {video_id}")
        except Exception as e:
            logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        return "", []
 
    def _sleep(self):
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))