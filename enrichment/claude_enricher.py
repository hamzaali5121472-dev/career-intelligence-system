"""
Claude AI Enricher — B2Have Career Intelligence System
Uses Claude Haiku (fast, cheap) to enrich each collected post/article with:
  - Theme classification (18 themes)
  - Relevance score (0-10)
  - Power quote extraction
  - Audience segment identification (6 segments)
  - Coaching opportunity flag + reason
  - Cross-platform signal strength

Processes all raw JSON files in data/raw/ that haven't been enriched yet.
Output: JSON file per run → data/enriched/enriched_YYYYMMDD_HHMMSS.json
"""

import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from enrichment.themes import (
    CAREER_THEMES, THEME_DESCRIPTIONS,
    AUDIENCE_SEGMENTS, AUDIENCE_DESCRIPTIONS
)
from enrichment.deduplicator import filter_new_items

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/enricher.log", mode="a")
    ]
)
log = logging.getLogger("claude_enricher")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_ENRICHED = ROOT / "data" / "enriched"
DATA_ENRICHED.mkdir(parents=True, exist_ok=True)

# ── Prompt Template ───────────────────────────────────────────────────────────
ENRICHMENT_PROMPT = """You are an expert career coaching analyst for B2Have, a Toronto-based career coaching company.
Analyze the following post/article and return a JSON object with these exact fields.

CAREER THEMES (pick the SINGLE best match):
{themes_list}

AUDIENCE SEGMENTS (pick the SINGLE best match):
{segments_list}

POST/ARTICLE TO ANALYZE:
---
Title: {title}

Content: {content}

Source: {source} | Engagement: {engagement}
---

Return ONLY a valid JSON object, no explanation, no markdown:
{{
  "theme": "one theme from the list above",
  "relevance_score": <integer 0-10, where 10=directly about career coaching pain, 0=not relevant>,
  "power_quote": "<the single most compelling, emotionally resonant sentence from the content — exact words, max 150 chars>",
  "audience_segment": "one segment from the list above",
  "coaching_flag": <true if this person clearly needs/wants professional career coaching help, false otherwise>,
  "coaching_reason": "<1 sentence: why this person would benefit from coaching, or empty string if not applicable>",
  "sentiment": "frustrated|hopeful|angry|confused|desperate|neutral|positive",
  "urgency": "high|medium|low",
  "canada_relevant": <true if content is specifically relevant to Canadian/GTA job seekers, false otherwise>,
  "content_angle": "<1-sentence description of what content this insight could inspire for B2Have>",
  "summary": "<2-sentence plain English summary of what this post is about>"
}}"""

THEME_LIST_TEXT = "\n".join(
    f"- {name}: {desc}"
    for name, desc in THEME_DESCRIPTIONS.items()
)

SEGMENT_LIST_TEXT = "\n".join(
    f"- {name}: {desc}"
    for name, desc in AUDIENCE_DESCRIPTIONS.items()
)


def prepare_content_for_enrichment(item):
    """
    Extract the text content from an item (handles Reddit posts, RSS articles, etc.)
    Caps at 2000 chars — enough context without wasting tokens.
    """
    source = item.get("source", "unknown")

    if source == "reddit":
        title = item.get("title", "")
        body = item.get("body", "")[:1500]
        top_comments = item.get("top_comments", [])

        comment_text = ""
        for i, c in enumerate(top_comments[:3]):
            comment_text += f"\nComment {i+1} ({c.get('score', 0)} upvotes): {c.get('body', '')[:300]}"

        return title, f"{body}{comment_text}"[:2000]

    elif source == "rss":
        title = item.get("title", "")
        body = item.get("full_text") or item.get("summary", "")
        return title, body[:2000]

    else:
        title = item.get("title", "") or item.get("name", "")
        body = item.get("body", "") or item.get("description", "") or item.get("summary", "")
        return title, body[:2000]


def format_engagement(item):
    """Summarize engagement metrics as a short string."""
    parts = []
    if item.get("score"):
        parts.append(f"{item['score']} upvotes")
    if item.get("num_comments"):
        parts.append(f"{item['num_comments']} comments")
    if item.get("upvote_ratio"):
        parts.append(f"{int(item['upvote_ratio'] * 100)}% upvoted")
    return " | ".join(parts) if parts else "N/A"


def enrich_item(client, item):
    """
    Send one item to Claude Haiku for enrichment.
    Returns the enrichment dict, or None on failure.
    """
    title, content = prepare_content_for_enrichment(item)

    if not content and not title:
        return None

    prompt = ENRICHMENT_PROMPT.format(
        themes_list=THEME_LIST_TEXT,
        segments_list=SEGMENT_LIST_TEXT,
        title=title,
        content=content,
        source=item.get("source", "unknown"),
        engagement=format_engagement(item)
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parse JSON — handle any markdown wrapping
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        enrichment = json.loads(response_text)

        # Validate required fields
        required = ["theme", "relevance_score", "power_quote", "audience_segment",
                    "coaching_flag", "summary"]
        for field in required:
            if field not in enrichment:
                enrichment[field] = None

        return enrichment

    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error for item {item.get('id', '?')}: {e}")
        return None
    except Exception as e:
        log.error(f"Enrichment API error for item {item.get('id', '?')}: {e}")
        return None


def load_raw_files(since_hours=25):
    """
    Load all raw JSON files from data/raw/ collected in the last N hours.
    Returns flat list of all items across all files.
    """
    all_items = []
    cutoff = datetime.now(timezone.utc).timestamp() - (since_hours * 3600)

    for filepath in sorted(DATA_RAW.glob("*.json")):
        # Check file modification time
        if filepath.stat().st_mtime < cutoff:
            continue

        try:
            with open(filepath) as f:
                data = json.load(f)

            # Handle both reddit (posts key) and rss (articles key) formats
            items = data.get("posts") or data.get("articles") or []
            for item in items:
                item["_source_file"] = filepath.name
            all_items.extend(items)
            log.info(f"Loaded {len(items)} items from {filepath.name}")

        except Exception as e:
            log.error(f"Could not load {filepath}: {e}")

    return all_items


def run_enrichment(since_hours=25):
    """
    Main enrichment run.
    Loads recent raw data, deduplicates, enriches with Claude Haiku, saves output.
    """
    log.info("=" * 60)
    log.info("Claude AI Enricher — B2Have Career Intelligence")
    log.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # Load Anthropic client
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    min_score = int(os.getenv("MIN_RELEVANCE_SCORE", 6))

    # Load raw data
    raw_items = load_raw_files(since_hours=since_hours)
    log.info(f"Total raw items to process: {len(raw_items)}")

    # Deduplicate — only process items we haven't seen before
    new_items, dupe_count = filter_new_items(raw_items)
    log.info(f"After deduplication: {len(new_items)} new items ({dupe_count} duplicates skipped)")

    if not new_items:
        log.info("No new items to enrich. Exiting.")
        return None, {}

    # Enrich each item
    enriched_items = []
    skipped_low_score = 0
    api_errors = 0

    for i, item in enumerate(new_items):
        log.info(f"  Enriching {i+1}/{len(new_items)}: {item.get('title', 'untitled')[:60]}...")

        enrichment = enrich_item(client, item)

        if enrichment is None:
            api_errors += 1
            continue

        score = enrichment.get("relevance_score", 0)

        if score < min_score:
            skipped_low_score += 1
            log.debug(f"  Skipped (score {score} < {min_score}): {item.get('title', '')[:50]}")
            continue

        # Merge enrichment into item
        enriched_item = {
            **item,
            "enrichment": enrichment,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "relevance_score": score,
            "theme": enrichment.get("theme"),
            "audience_segment": enrichment.get("audience_segment"),
            "coaching_flag": enrichment.get("coaching_flag", False),
            "power_quote": enrichment.get("power_quote")
        }

        enriched_items.append(enriched_item)

        # Rate limit: ~60 requests/minute for Haiku — small delay
        if i % 10 == 9:
            time.sleep(1)

    # Save enriched output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = DATA_ENRICHED / f"enriched_{timestamp}.json"

    theme_counts = {}
    for item in enriched_items:
        t = item.get("theme", "unknown")
        theme_counts[t] = theme_counts.get(t, 0) + 1

    output = {
        "metadata": {
            "enricher": "claude-haiku-4-5",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_raw_items": len(raw_items),
            "new_items": len(new_items),
            "enriched_items": len(enriched_items),
            "skipped_low_score": skipped_low_score,
            "api_errors": api_errors,
            "min_relevance_score": min_score,
            "theme_distribution": theme_counts
        },
        "items": enriched_items
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Summary
    log.info("=" * 60)
    log.info(f"ENRICHMENT COMPLETE")
    log.info(f"Enriched items saved: {len(enriched_items)}")
    log.info(f"Skipped (low score): {skipped_low_score}")
    log.info(f"API errors: {api_errors}")
    log.info(f"Output: {output_file}")
    log.info("Top themes:")
    for theme, count in sorted(theme_counts.items(), key=lambda x: -x[1])[:5]:
        log.info(f"  {theme}: {count}")
    log.info("=" * 60)

    return str(output_file), output["metadata"]


if __name__ == "__main__":
    run_enrichment()
