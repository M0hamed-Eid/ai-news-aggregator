# app/scrapers/blog_scraper.py

# How this scraper works:
# Both Anthropic and OpenAI publish their news/research via RSS feeds.
# We use feedparser (same as the YouTube scraper) to get article metadata,
# then requests + convert to fetch the actual article content.
#
# Why not just use the RSS description?
# RSS descriptions are often truncated summaries (1-2 sentences).
# We want the full article text so the curator agent has enough content to work with.

# Two scraping strategies:
#
# OpenAI  → RSS feed (feedparser) + requests with proxy + random delay.
#
# Anthropic → No working RSS. Their /news page is React/Next.js (JS-rendered),
#              so plain requests gets an empty HTML shell.
#              We use Playwright (headless Chromium) to fully render the page,
#              then extract article cards directly from the DOM.

# Key fixes in this version:
#   1. ConversionResult.content  ← correct attribute (not .markdown, not str())
#   2. Playwright: snapshot ALL card data (href, title, date) before navigating
#      to any article — avoids "execution context was destroyed" crash

import feedparser
import requests
import logging
import time
import random
import os
from datetime import datetime, timezone
from typing import List
 
from html_to_markdown import convert
 
from app.scrapers.base_scraper import BaseScraper, ScrapedArticle
 
logger = logging.getLogger(__name__)
 
MAX_ARTICLE_CHARS = 8000
REQUEST_TIMEOUT   = 15
MIN_DELAY = 1.5
MAX_DELAY = 3.5
 
PROXY_URL          = os.getenv("RESIDENTIAL_PROXY_URL", "")
OPENAI_RSS         = "https://openai.com/news/rss.xml"
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"
 
 
class BlogScraper(BaseScraper):
 
    def __init__(self):
        super().__init__(source_name="blog")
        self._proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        status = f"proxy={PROXY_URL}" if PROXY_URL else "no proxy"
        logger.info(f"Blog scraper: {status}")
 
    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
 
    def scrape(self, hours_lookback: int) -> List[ScrapedArticle]:
        all_articles = []
 
        logger.info("Scraping blog: Anthropic (Playwright)")
        anthropic = self._scrape_anthropic(hours_lookback)
        logger.info(f"  Found {len(anthropic)} recent articles from Anthropic")
        all_articles.extend(anthropic)
 
        logger.info("Scraping blog: OpenAI (RSS + requests)")
        openai = self._scrape_openai_rss(hours_lookback)
        logger.info(f"  Found {len(openai)} recent articles from OpenAI")
        all_articles.extend(openai)
 
        logger.info(f"Blog scraper finished. Total: {len(all_articles)}")
        return all_articles
 
    # ------------------------------------------------------------------
    # Anthropic — Playwright
    # ------------------------------------------------------------------
 
    def _scrape_anthropic(self, hours_lookback: int) -> List[ScrapedArticle]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run:\n"
                "  uv add playwright\n"
                "  python -m playwright install chromium"
            )
            return []
 
        articles = []
 
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
 
                context_kwargs = {
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                }
                if PROXY_URL:
                    context_kwargs["proxy"] = {"server": PROXY_URL}
 
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
 
                logger.info(f"  Playwright: loading {ANTHROPIC_NEWS_URL}")
                page.goto(ANTHROPIC_NEWS_URL, wait_until="networkidle", timeout=30_000)
                page.wait_for_selector("a[href*='/news/']", timeout=15_000)
 
                # -------------------------------------------------------
                # CRITICAL FIX: extract ALL data as plain Python values
                # (strings, not ElementHandle objects) BEFORE navigating
                # to any article page. ElementHandles become invalid the
                # moment the page navigates — that's the "execution context
                # was destroyed" error we saw before.
                # -------------------------------------------------------
                card_data = page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a[href*="/news/"]');
                        const seen  = new Set();
                        const cards = [];
                        for (const a of links) {
                            const href = a.getAttribute('href') || '';
                            if (!href || seen.has(href)) continue;
                            if (href.replace(/\\/+/g,'') === 'news') continue;
                            seen.add(href);
 
                            const url = href.startsWith('http')
                                ? href
                                : 'https://www.anthropic.com' + href;
 
                            // First non-empty text line = title
                            const title = (a.innerText || '').trim().split('\\n')[0] || url;
 
                            // Find <time> anywhere inside the anchor
                            const timeEl = a.querySelector('time');
                            const dateStr = timeEl
                                ? (timeEl.getAttribute('datetime') || timeEl.innerText || '')
                                : '';
 
                            cards.push({ url, title, dateStr });
                        }
                        return cards;
                    }
                """)
 
                for card in card_data:
                    url      = card.get("url", "")
                    title    = card.get("title", url.split("/")[-1])
                    date_str = card.get("dateStr", "")
 
                    if not date_str:
                        continue  # no date = can't filter by recency
 
                    published_at = self._parse_date(date_str)
                    if not self._is_recent(published_at, hours_lookback):
                        continue
 
                    self._sleep()
 
                    # Navigate to the article — safe now because we already
                    # captured all card data as plain Python strings above
                    content = self._fetch_article_playwright(page, url)
                    if not content:
                        logger.warning(f"  No content for: {title}")
                        continue
 
                    articles.append(ScrapedArticle(
                        title=title,
                        url=url,
                        content=content,
                        source="blog_anthropic",
                        channel_or_author="Anthropic",
                        published_at=published_at,
                        video_id=None,
                    ))
 
                browser.close()
 
        except Exception as e:
            logger.error(f"Playwright scraping failed: {e}")
 
        return articles
 
    def _fetch_article_playwright(self, page, url: str) -> str:
        try:
            page.goto(url, wait_until="networkidle", timeout=20_000)
            el   = page.query_selector("article") or page.query_selector("main")
            text = el.inner_text() if el else page.inner_text()
            text = text.strip()
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "... [article truncated]"
            return text
        except Exception as e:
            logger.warning(f"  Could not fetch {url}: {e}")
            return ""
 
    # ------------------------------------------------------------------
    # OpenAI — RSS + requests
    # ------------------------------------------------------------------
 
    def _scrape_openai_rss(self, hours_lookback: int) -> List[ScrapedArticle]:
        feed = feedparser.parse(OPENAI_RSS)
        if not feed.entries:
            logger.warning(f"No entries in OpenAI RSS: {OPENAI_RSS}")
            return []
 
        articles = []
        for entry in feed.entries:
            time_struct = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )
            if not time_struct:
                continue
 
            published_at = datetime(*time_struct[:6], tzinfo=timezone.utc)
            if not self._is_recent(published_at, hours_lookback):
                continue
 
            url = entry.get("link", "")
            if not url:
                continue
 
            self._sleep()
            content = self._fetch_article_requests(url)
 
            if not content:
                content = entry.get("summary", "")
                if content:
                    logger.info(f"  RSS summary fallback: {entry.get('title')}")
 
            if not content:
                logger.warning(f"  No content for: {entry.get('title', 'unknown')}")
                continue
 
            articles.append(ScrapedArticle(
                title=entry.get("title", "Untitled"),
                url=url,
                content=content,
                source="blog_openai",
                channel_or_author="OpenAI",
                published_at=published_at,
                video_id=None,
            ))
 
        return articles
 
    def _fetch_article_requests(self, url: str) -> str:
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                proxies=self._proxies,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
 
            # html-to-markdown 3.x returns ConversionResult (a Rust-backed object).
            # The markdown text lives in  result.content  (NOT .markdown, NOT str())
            result = convert(response.text)
            text   = result.content or ""
 
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "... [article truncated]"
            return text.strip()
 
        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout: {url}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"  HTTP {e.response.status_code}: {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"  Request error: {url}: {e}")
        except Exception as e:
            logger.error(f"  Unexpected error: {url}: {e}")
        return ""
 
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
 
    def _sleep(self):
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
 
    def _parse_date(self, dt_str: str) -> datetime:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ):
            try:
                return datetime.strptime(dt_str.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        logger.warning(f"  Unparseable date '{dt_str}', using now()")
        return datetime.now(timezone.utc)