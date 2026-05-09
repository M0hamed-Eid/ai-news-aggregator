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
from app.scrapers.blog_scraper import BlogScraper
from app.config import config

def print_articles(articles, label):
    print(f"\n{'='*50}")
    print(f"{label}: {len(articles)} articles")
    print(f"{'='*50}\n")
    for article in articles:
        print(f"Title:   {article.title}")
        print(f"Source:  {article.channel_or_author}")
        print(f"URL:     {article.url}")
        print(f"Date:    {article.published_at}")
        print(f"Content: {article.content[:200]}...")
        print("-" * 50)

if __name__ == "__main__":
    hours = config.scraper.hours_lookback
 
    # --- YouTube ---
    yt_scraper = YouTubeScraper()
    yt_articles = yt_scraper.scrape(hours_lookback=hours)
    print_articles(yt_articles, "YouTube")
 
    # --- Blogs (Anthropic + OpenAI) ---
    blog_scraper = BlogScraper()
    blog_articles = blog_scraper.scrape(hours_lookback=hours)
    print_articles(blog_articles, "Blogs")
 
    # --- Combined ---
    all_articles = yt_articles + blog_articles
    print(f"\nTotal across all sources: {len(all_articles)} articles")
