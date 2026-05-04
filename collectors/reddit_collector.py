"""
Reddit Collector — B2Have Career Intelligence System
Collects posts from career-related subreddits using PRAW (official Reddit API).

Collects: hot + new posts, full post body, top comments with replies,
          engagement counts (upvotes, comments, awards), author context.

Output: JSON file per run → data/raw/reddit_YYYYMMDD_HHMMSS.json
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/reddit_collector.log", mode="a")
    ]
)
log = logging.getLogger("reddit_collector")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load subreddit and keyword configs."""
    with open(CONFIG_DIR / "subreddits.json") as f:
        sub_config = json.load(f)
    with open(CONFIG_DIR / "keywords.json") as f:
        kw_config = json.load(f)
    with open(CONFIG_DIR / "thresholds.json") as f:
        thresholds = json.load(f)
    return sub_config, kw_config, thresholds


def build_keyword_set(kw_config):
    """Flatten all theme keywords into a single searchable set (lowercase)."""
    keywords = set()
    for theme_data in kw_config["themes"].values():
        for kw in theme_data["keywords"]:
            keywords.add(kw.lower())
    for kw in kw_config["global_career_keywords"]:
        keywords.add(kw.lower())
    return keywords


def matches_keywords(text, keyword_set):
    """Return True if any keyword appears in the text."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in keyword_set)


def get_matched_themes(text, kw_config):
    """Return list of theme names that match this text."""
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for theme_name, theme_data in kw_config["themes"].items():
        for kw in theme_data["keywords"]:
            if kw.lower() in text_lower:
                matched.append(theme_name)
                break
    return matched


def content_hash(text):
    """SHA-256 fingerprint for deduplication."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def get_top_comments(post, n=5, min_score=1):
    """
    Fetch top N comments with their top reply.
    Returns structured list with full comment text — never truncated.
    """
    comments = []
    try:
        post.comments.replace_more(limit=0)  # Don't expand 'load more' to save time
        sorted_comments = sorted(
            [c for c in post.comments.list() if hasattr(c, 'score') and c.score >= min_score],
            key=lambda c: c.score,
            reverse=True
        )[:n]

        for comment in sorted_comments:
            top_reply = None
            if hasattr(comment, 'replies') and comment.replies:
                for reply in comment.replies:
                    if hasattr(reply, 'score'):
                        top_reply = {
                            "body": reply.body,
                            "score": reply.score,
                            "author": str(reply.author) if reply.author else "[deleted]"
                        }
                        break

            comments.append({
                "body": comment.body,
                "score": comment.score,
                "author": str(comment.author) if comment.author else "[deleted]",
                "created_utc": comment.created_utc,
                "top_reply": top_reply
            })
    except Exception as e:
        log.warning(f"Could not fetch comments for post {post.id}: {e}")

    return comments


def collect_subreddit(reddit, sub_config, keyword_set, kw_config, thresholds):
    """
    Collect posts from one subreddit.
    Returns list of post dicts with full context.
    """
    sub_name = sub_config["name"]
    limit = sub_config.get("collection_limit", 100)
    min_score = sub_config.get("min_score", 50)
    requires_keyword = sub_config.get("keyword_filter_required", False)
    reddit_thresholds = thresholds["collection_thresholds"]["reddit"]

    log.info(f"  Collecting r/{sub_name} (limit={limit}, min_score={min_score})")

    collected = []
    seen_hashes = set()

    try:
        subreddit = reddit.subreddit(sub_name)

        # Collect from both hot and new
        all_posts = []
        all_posts.extend(list(subreddit.hot(limit=limit)))
        all_posts.extend(list(subreddit.new(limit=int(limit * 0.3))))

        for post in all_posts:
            # Skip posts that don't meet score threshold
            if post.score < min_score:
                continue

            # Skip posts older than max age
            age_hours = (datetime.now(timezone.utc).timestamp() - post.created_utc) / 3600
            if age_hours > reddit_thresholds.get("max_post_age_hours", 72):
                continue

            # Combine title + body for keyword matching
            full_text = f"{post.title} {post.selftext}"

            # Apply keyword filter if required (e.g. r/canada, r/toronto)
            if requires_keyword and not matches_keywords(full_text, keyword_set):
                continue

            # Dedup by content hash
            post_hash = content_hash(post.title + post.selftext[:200])
            if post_hash in seen_hashes:
                continue
            seen_hashes.add(post_hash)

            # Detect matched themes
            matched_themes = get_matched_themes(full_text, kw_config)

            # Collect top comments with full text
            top_comments = get_top_comments(post, n=5)

            post_data = {
                "id": post.id,
                "content_hash": post_hash,
                "source": "reddit",
                "subreddit": sub_name,
                "title": post.title,
                "body": post.selftext if post.selftext else "",
                "url": f"https://reddit.com{post.permalink}",
                "external_url": post.url if not post.url.startswith("https://www.reddit.com") else None,
                "score": post.score,
                "upvote_ratio": post.upvote_ratio,
                "num_comments": post.num_comments,
                "awards": post.total_awards_received,
                "flair": post.link_flair_text,
                "author": str(post.author) if post.author else "[deleted]",
                "created_utc": post.created_utc,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "age_hours": round(age_hours, 1),
                "top_comments": top_comments,
                "matched_themes_preliminary": matched_themes,
                "is_self_post": post.is_self,
                "nsfw": post.over_18
            }

            collected.append(post_data)

        log.info(f"  ✓ r/{sub_name}: {len(collected)} posts collected")

    except Exception as e:
        log.error(f"  ✗ r/{sub_name}: FAILED — {e}")

    return collected


def run_collection():
    """
    Main collection function.
    Connects to Reddit, iterates all configured subreddits, saves JSON output.
    """
    log.info("=" * 60)
    log.info("Reddit Collector — B2Have Career Intelligence")
    log.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # Load configs
    sub_config, kw_config, thresholds = load_config()
    keyword_set = build_keyword_set(kw_config)
    log.info(f"Loaded {len(keyword_set)} keywords across {len(kw_config['themes'])} themes")

    # Connect to Reddit
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "b2have_career_intel/1.0").strip(),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD")
    )
    log.info(f"Connected to Reddit as: {reddit.user.me()}")

    # Collect from all subreddits
    all_posts = []
    health_report = {}

    for sub in sub_config["subreddits"]:
        try:
            posts = collect_subreddit(reddit, sub, keyword_set, kw_config, thresholds)
            all_posts.extend(posts)
            health_report[sub["name"]] = {
                "status": "success",
                "items_collected": len(posts),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            log.error(f"Subreddit {sub['name']} failed: {e}")
            health_report[sub["name"]] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    # Save output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = DATA_RAW / f"reddit_{timestamp}.json"

    output = {
        "metadata": {
            "collector": "reddit",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_posts": len(all_posts),
            "subreddits_collected": len([s for s in health_report.values() if s["status"] == "success"]),
            "subreddits_failed": len([s for s in health_report.values() if s["status"] == "failed"])
        },
        "health_report": health_report,
        "posts": all_posts
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Summary
    log.info("=" * 60)
    log.info(f"COLLECTION COMPLETE")
    log.info(f"Total posts collected: {len(all_posts)}")
    log.info(f"Output saved: {output_file}")
    log.info("Health summary:")
    for sub_name, report in health_report.items():
        status_icon = "✓" if report["status"] == "success" else "✗"
        items = report.get("items_collected", 0)
        log.info(f"  {status_icon} r/{sub_name}: {items} posts")
    log.info("=" * 60)

    return str(output_file), health_report


if __name__ == "__main__":
    run_collection()
