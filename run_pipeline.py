# run_pipeline.py

import logging

# basicConfig sets up the logging system for the whole application.
# Every logger.info() / logger.warning() call in every file will use this format.
# %(asctime)s   = timestamp
# %(name)s      = which file/module logged this (e.g. "app.scrapers.youtube_scraper")
# %(levelname)s = INFO / WARNING / ERROR
# %(message)s   = the actual message
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

# Quick test — we'll expand this file as we build each phase
from app.scrapers.youtube_scraper import YouTubeScraper
from app.config import config

if __name__ == "__main__":
    scraper = YouTubeScraper()
    articles = scraper.scrape(hours_lookback=config.scraper.hours_lookback)

    print(f"\n{'='*50}")
    print(f"Scraped {len(articles)} articles")
    print(f"{'='*50}\n")

    for article in articles:
        print(f"Title:    {article.title}")
        print(f"Channel:  {article.channel_or_author}")
        print(f"URL:      {article.url}")
        print(f"Date:     {article.published_at}")
        print(f"Content:  {article.content[:200]}...")
        print("-" * 50)