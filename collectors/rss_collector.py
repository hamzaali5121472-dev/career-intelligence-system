"""
RSS Feed Collector — B2Have Career Intelligence System
Collects articles from 13 career/HR/job market news sources via RSS.

Fetches full article text where possible. Filters by age, keyword relevance.
Output: JSON file per run → data/raw/rss_YYYYMMDD_HHMMSS.json
"""

import os
import json
import hashlib
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import socket
import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Global socket timeout — no single feed can block longer than this
socket.setdefaulttimeout(20)

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/rss_collector.log", mode="a")
    ]
)
log = logging.getLogger("rss_collector")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "B2Have Career Intelligence RSS Reader/1.0 (career coaching research)"
}


def load_config():
    with open(CONFIG_DIR / "rss_feeds.json") as f:
        rss_config = json.load(f)
    with open(CONFIG_DIR / "keywords.json") as f:
        kw_config = json.load(f)
    with open(CONFIG_DIR / "thresholds.json") as f:
        thresholds = json.load(f)
    return rss_config, kw_config, thresholds


def build_keyword_set(kw_config):
    keywords = set()
    for theme_data in kw_config["themes"].values():
        for kw in theme_data["keywords"]:
            keywords.add(kw.lower())
    for kw in kw_config["global_career_keywords"]:
        keywords.add(kw.lower())
    return keywords


def matches_keywords(text, keyword_set):
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in keyword_set)


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def parse_entry_date(entry):
    """Parse publication date from feedparser entry. Returns datetime or None."""
    for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
        parsed = getattr(entry, date_field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_full_article_text(url, timeout=15):
    """
    Fetch and extract main article text from a URL.
    Uses BeautifulSoup to extract article body, stripping nav/ads/footer.
    Returns cleaned text or None on failure.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise elements
        for tag in soup(["nav", "header", "footer", "aside", "script",
                          "style", "advertisement", "noscript"]):
            tag.decompose()

        # Try common article body selectors in priority order
        selectors = [
            "article",
            "[class*='article-body']",
            "[class*='post-content']",
            "[class*='entry-content']",
            "[class*='story-body']",
            "main",
            ".content"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator="\n", strip=True)
                if len(text) > 200:
                    return text[:8000]  # Cap at 8000 chars for deep enrichment

        # Fallback: grab all paragraph text
        paragraphs = soup.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
        return text[:8000] if len(text) > 200 else None

    except Exception as e:
        log.debug(f"Could not fetch full text from {url}: {e}")
        return None


def collect_feed(feed_config, keyword_set, max_age_days=7, fetch_full=False):
    """
    Collect articles from one RSS feed.
    Returns list of article dicts.
    """
    feed_name = feed_config["name"]
    feed_url = feed_config["url"]
    do_fetch_full = feed_config.get("fetch_full_text", False) and fetch_full

    log.info(f"  Collecting: {feed_name}")
    collected = []
    seen_hashes = set()
    max_age = timedelta(days=max_age_days)
    cutoff = datetime.now(timezone.utc) - max_age

    try:
        # Try fetching with requests first (allows custom headers), fallback to feedparser direct
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=(8, 15))
            feed = feedparser.parse(resp.content)
        except Exception:
            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                log.warning(f"  ⚠ {feed_name}: Could not fetch feed — {e}")
                return collected, "failed", str(e)

        if feed.bozo and not feed.entries:
            log.warning(f"  ⚠ {feed_name}: Feed parse error (no entries) — {feed.bozo_exception}")
            return collected, "failed", str(feed.bozo_exception)
        elif feed.bozo and feed.entries:
            # Bozo but still has entries — common with charset warnings, proceed
            log.debug(f"  {feed_name}: Minor parse warning (still has entries) — {feed.bozo_exception}")

        max_per_feed = feed_config.get("max_articles", 30)
        for entry in feed.entries[:max_per_feed]:  # Max 30 articles per feed
            # Parse date
            pub_date = parse_entry_date(entry)

            # Skip old articles
            if pub_date and pub_date < cutoff:
                continue

            # Extract basic fields
            title = getattr(entry, "title", "") or ""
            summary = getattr(entry, "summary", "") or ""
            link = getattr(entry, "link", "") or ""
            author = getattr(entry, "author", "") or ""

            # Clean summary of HTML tags
            if summary:
                summary_clean = BeautifulSoup(summary, "html.parser").get_text(strip=True)
            else:
                summary_clean = ""

            # Combine title + summary for keyword matching
            # For high-priority feeds (thought leadership, job market data), be more permissive
            full_text_preview = f"{title} {summary_clean}"
            feed_category = feed_config.get("category", "")
            high_priority = feed_config.get("priority", "") == "high"

            if not matches_keywords(full_text_preview, keyword_set):
                # Still include high-priority feed items about work/jobs even without exact keyword match
                if not (high_priority and any(kw in full_text_preview.lower()
                        for kw in ["work", "job", "career", "employee", "worker", "hire",
                                   "salary", "boss", "office", "manager", "remote"])):
                    continue

            # Dedup
            article_hash = content_hash(title + link)
            if article_hash in seen_hashes:
                continue
            seen_hashes.add(article_hash)

            # Optionally fetch full article text
            full_text = None
            if do_fetch_full and link:
                full_text = fetch_full_article_text(link)
                time.sleep(1)  # Polite delay between requests

            article_data = {
                "id": content_hash(link or title),
                "content_hash": article_hash,
                "source": "rss",
                "feed_name": feed_name,
                "feed_category": feed_config.get("category", "unknown"),
                "title": title,
                "summary": summary_clean,
                "full_text": full_text,
                "url": link,
                "author": author,
                "published_at": pub_date.isoformat() if pub_date else None,
                "collected_at": datetime.now(timezone.utc).isoformat()
            }

            collected.append(article_data)

        log.info(f"  ✓ {feed_name}: {len(collected)} articles")
        return collected, "success", None

    except Exception as e:
        log.error(f"  ✗ {feed_name}: FAILED — {e}")
        return collected, "failed", str(e)


def run_collection():
    """Main RSS collection run."""
    log.info("=" * 60)
    log.info("RSS Collector — B2Have Career Intelligence")
    log.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    rss_config, kw_config, thresholds = load_config()
    keyword_set = build_keyword_set(kw_config)
    max_age = thresholds["collection_thresholds"]["rss"]["max_article_age_days"]

    all_articles = []
    health_report = {}

    for feed in rss_config["feeds"]:
        articles, status, error = collect_feed(
            feed, keyword_set, max_age_days=max_age, fetch_full=True
        )
        all_articles.extend(articles)
        health_report[feed["name"]] = {
            "status": status,
            "items_collected": len(articles),
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        time.sleep(0.5)  # Polite delay between feeds

    # Save output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = DATA_RAW / f"rss_{timestamp}.json"

    output = {
        "metadata": {
            "collector": "rss",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_articles": len(all_articles),
            "feeds_collected": len([f for f in health_report.values() if f["status"] == "success"]),
            "feeds_failed": len([f for f in health_report.values() if f["status"] == "failed"])
        },
        "health_report": health_report,
        "articles": all_articles
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info("=" * 60)
    log.info(f"RSS COLLECTION COMPLETE — {len(all_articles)} articles")
    log.info(f"Output saved: {output_file}")
    log.info("=" * 60)

    return str(output_file), health_report


if __name__ == "__main__":
    run_collection()
