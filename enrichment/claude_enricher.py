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
ENRICHMENT_PROMPT = """You are a senior career coaching analyst at B2Have, a Toronto-based career coaching firm serving the GTA/Ontario market. Your clients are mid-career professionals, senior executives, and new graduates navigating job searches, career pivots, and workplace challenges.

Analyze the following post/article deeply and return a rich JSON object. This analysis will be read by a career coach who needs to understand: what real people are struggling with, exact language clients use, and what content/services to create.

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

Return ONLY a valid JSON object, no explanation, no markdown. Be specific, detailed, and thorough in every field:
{{
  "theme": "one theme from the list above",
  "relevance_score": <integer 0-10, where 10=directly about career coaching pain in GTA/Canada, 0=not relevant at all>,
  "power_quote": "<the single most emotionally resonant, shareable sentence from the content — exact words if possible, max 180 chars>",
  "audience_segment": "one segment from the list above",
  "coaching_flag": <true if this reveals a real pain point where professional career coaching would genuinely help, false otherwise>,
  "coaching_reason": "<1-2 sentences: the specific career challenge this person faces and what a B2Have coach would help them do>",
  "sentiment": "frustrated|hopeful|angry|confused|desperate|neutral|positive|anxious",
  "urgency": "high|medium|low",
  "canada_relevant": <true if specifically relevant to Canadian/GTA/Ontario job seekers or employers, false if US-only>,
  "canada_context": "<1 sentence on how this applies specifically to the GTA/Ontario market, or empty string if not relevant>",
  "summary": "<4-5 sentence detailed summary: what happened, the key data/findings, who is affected, what it means for job seekers>",
  "key_statistics": ["<stat 1 with number>", "<stat 2 with number>", "<stat 3 with number>"],
  "what_clients_say": ["<exact phrase a client would use when describing this pain>", "<another phrase>", "<another phrase>"],
  "coaching_questions": ["<question a coach would ask to explore this with a client>", "<another question>", "<another question>"],
  "linkedin_hooks": ["<compelling opening line for a LinkedIn post on this topic>", "<alternative hook>"],
  "content_angles": ["<specific content idea for B2Have (blog post, video, workshop)>", "<another angle>", "<another angle>"]
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
        # Use full_text if available, fall back to summary.
        # Cap at 2500 chars — enough for rich analysis without risking
        # Haiku truncating the JSON output at 1500 max_tokens.
        body = item.get("full_text") or item.get("summary", "")
        return title, body[:2500]

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


def _call_haiku(client, prompt):
    """
    Call Claude Haiku and return (response_text, stop_reason).
    Raises exceptions on API failures.
    """
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = message.content[0].text.strip()
    stop_reason = message.stop_reason  # "end_turn" or "max_tokens"
    return response_text, stop_reason


def _parse_json_response(response_text):
    """Strip markdown fencing and parse JSON. Returns dict."""
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    return json.loads(response_text.strip())


def enrich_item(client, item):
    """
    Send one item to Claude Haiku for enrichment.
    Returns the enrichment dict, or None on failure.

    If the response is truncated (stop_reason = 'max_tokens') or the JSON
    fails to parse, automatically retries with a much shorter content snippet
    (title + 500 chars) so the output JSON fits within the token budget.
    """
    title, content = prepare_content_for_enrichment(item)

    if not content and not title:
        return None

    def _build_prompt(content_text):
        return ENRICHMENT_PROMPT.format(
            themes_list=THEME_LIST_TEXT,
            segments_list=SEGMENT_LIST_TEXT,
            title=title,
            content=content_text,
            source=item.get("source", "unknown"),
            engagement=format_engagement(item)
        )

    # ── First attempt ─────────────────────────────────────────────────────────
    try:
        response_text, stop_reason = _call_haiku(client, _build_prompt(content))

        if stop_reason == "max_tokens":
            # Output was cut off — truncated JSON will fail to parse.
            # Log and fall through to retry with less input.
            log.warning(
                f"Haiku hit max_tokens for '{title[:50]}' — retrying with shorter content"
            )
            raise json.JSONDecodeError("truncated", "", 0)

        enrichment = _parse_json_response(response_text)

    except json.JSONDecodeError:
        # ── Retry with just title + first 500 chars ────────────────────────
        log.info(f"  Retry (shorter content) for: {title[:60]}")
        try:
            short_content = content[:500]
            response_text, stop_reason = _call_haiku(client, _build_prompt(short_content))
            enrichment = _parse_json_response(response_text)
        except json.JSONDecodeError as e2:
            log.warning(f"JSON parse error (retry) for item {item.get('id', '?')}: {e2}")
            return None
        except Exception as e2:
            log.error(f"Enrichment API error (retry) for item {item.get('id', '?')}: {e2}")
            return None

    except Exception as e:
        log.error(f"Enrichment API error for item {item.get('id', '?')}: {e}")
        return None

    # ── Validate and fill defaults ────────────────────────────────────────────
    required = ["theme", "relevance_score", "power_quote", "audience_segment",
                "coaching_flag", "summary"]
    for field in required:
        if field not in enrichment:
            enrichment[field] = None
    # Default empty lists for array fields
    for list_field in ["key_statistics", "what_clients_say", "coaching_questions",
                       "linkedin_hooks", "content_angles"]:
        if list_field not in enrichment or not isinstance(enrichment[list_field], list):
            enrichment[list_field] = []

    return enrichment


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

        # Merge enrichment into item — surface key fields for easy access
        enriched_item = {
            **item,
            "enrichment": enrichment,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "relevance_score": score,
            "theme": enrichment.get("theme"),
            "audience_segment": enrichment.get("audience_segment"),
            "coaching_flag": enrichment.get("coaching_flag", False),
            "power_quote": enrichment.get("power_quote"),
            # Surface new deep-analysis fields at top level for doc formatter
            "key_statistics": enrichment.get("key_statistics", []),
            "what_clients_say": enrichment.get("what_clients_say", []),
            "coaching_questions": enrichment.get("coaching_questions", []),
            "linkedin_hooks": enrichment.get("linkedin_hooks", []),
            "content_angles": enrichment.get("content_angles", []),
            "canada_context": enrichment.get("canada_context", "")
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
