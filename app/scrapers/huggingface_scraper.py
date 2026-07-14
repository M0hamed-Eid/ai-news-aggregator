# app/scrapers/huggingface_scraper.py
#
# Hugging Face Hub — newest published models via the official REST API
# (huggingface.co/api/models). Confirmed live: no RSS/Atom feed exists for
# models or papers (only the HF blog has one, unrelated content), so this
# uses the documented JSON API, unauthenticated (500 req / 5 min is far more
# than a single scrape needs).
#
# sort=createdAt is a firehose — confirmed live it returns mostly low-effort
# test uploads (zero likes/downloads, no recognized library tag). Rather than
# flood the digest with noise, this over-fetches (huggingface_fetch_limit)
# and keeps only models that declare a recognized library_name.
#
# The list endpoint has no free-text description/README, so `content` is
# synthesized from the structured fields it does return — still genuinely
# informative digest-agent input, just not prose.
#
# Output maps directly onto the existing Article table:
#   title              -> "New model: {model_id}"
#   url                -> https://huggingface.co/{model_id}
#   content             -> synthesized from library/pipeline/tags/likes/downloads
#   channel_or_author  -> the model's namespace/org
#   source             -> "huggingface_model"

import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

from app.scrapers.base_scraper import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

HUGGINGFACE_MODELS_API_URL = "https://huggingface.co/api/models"


class HuggingFaceScraper(BaseScraper):

    def __init__(self, fetch_limit: int):
        super().__init__(source_name="huggingface_model")
        self.fetch_limit = fetch_limit

    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        try:
            response = requests.get(
                HUGGINGFACE_MODELS_API_URL,
                params={"sort": "createdAt", "direction": "-1", "limit": self.fetch_limit},
                timeout=15,
            )
            response.raise_for_status()
            models = response.json()
        except Exception as exc:
            logger.error(f"Hugging Face API request failed: {exc}")
            return []

        all_articles: List[ScrapedArticle] = []
        skipped_noise = 0

        for model in models:
            # Skip models with no recognized library — confirmed live these
            # are almost always throwaway test uploads, not real releases.
            if not model.get("library_name"):
                skipped_noise += 1
                continue

            published_at = self._parse_created(model.get("createdAt"))
            if published_at is None or not self._is_recent(published_at, hours_lookback):
                continue

            model_id = model.get("id") or model.get("modelId", "")
            if not model_id:
                continue

            all_articles.append(ScrapedArticle(
                title=f"New model: {model_id}",
                url=f"https://huggingface.co/{model_id}",
                content=self._build_content(model),
                source="huggingface_model",
                channel_or_author=model_id.split("/")[0] if "/" in model_id else "huggingface",
                published_at=published_at,
                video_id=None,
                image_url=None,
            ))

        logger.info(
            f"Hugging Face scraper finished. New models: {len(all_articles)} "
            f"(skipped {skipped_noise} with no recognized library)"
        )
        return all_articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_content(model: dict) -> str:
        library = model.get("library_name", "unspecified")
        pipeline = model.get("pipeline_tag", "unspecified")
        tags = ", ".join(model.get("tags", [])[:15]) or "none"
        likes = model.get("likes", 0)
        downloads = model.get("downloads", 0)
        return (
            f"New model published on Hugging Face Hub. "
            f"Library: {library}. Pipeline: {pipeline}. Tags: {tags}. "
            f"{likes} likes, {downloads} downloads so far."
        )

    @staticmethod
    def _parse_created(date_str: Optional[str]) -> Optional[datetime]:
        """Hugging Face returns e.g. "2026-07-12T15:14:14.000Z"."""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
