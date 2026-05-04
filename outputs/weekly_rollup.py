"""
Weekly Rollup — B2Have Career Intelligence System
Runs every Sunday evening. Reads all 7 daily enriched JSON files from the
past week and uses Claude Sonnet to synthesize a rich Weekly Narrative doc.

The Weekly Narrative is richer than any single daily brief — it finds:
  - Persistent themes that appeared across multiple days
  - The week's most important single signal
  - Patterns in what clients are struggling with
  - Recommended content priorities for next week
  - GTA/Canada market story for the week

Output: Google Doc "Career Intelligence — Weekly Narrative — Week of YYYY-MM-DD"

Usage:
  python outputs/weekly_rollup.py              # Rollup current week
  python outputs/weekly_rollup.py --week 2026-04-28   # Rollup specific week
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("weekly_rollup")

DATA_ENRICHED = ROOT / "data" / "enriched"

DIVIDER = "═" * 70


def get_current_week_monday():
    """Return Monday of the current week as YYYY-MM-DD string."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def load_week_enriched_items(week_monday_str):
    """
    Load all enriched items from the past 7 days starting from week_monday_str.
    Returns a flat list of all enriched items with their day label attached.
    """
    monday = datetime.strptime(week_monday_str, "%Y-%m-%d")
    week_days = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    all_items = []
    files_loaded = 0

    # Load enriched files from the past 8 days (generous window)
    cutoff = datetime.now(timezone.utc) - timedelta(days=8)

    for filepath in sorted(DATA_ENRICHED.glob("enriched_*.json"), reverse=True):
        if filepath.stat().st_mtime < cutoff.timestamp():
            continue
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            for item in items:
                # Tag with the file's date
                ts_str = filepath.stem.replace("enriched_", "")  # "20260504_171626"
                item_day = ts_str[:8]  # "20260504"
                try:
                    item["_day_label"] = datetime.strptime(item_day, "%Y%m%d").strftime("%Y-%m-%d")
                except Exception:
                    item["_day_label"] = "unknown"
            all_items.extend(items)
            files_loaded += 1
            log.info(f"Loaded {len(items)} items from {filepath.name}")
        except Exception as e:
            log.error(f"Could not load {filepath}: {e}")

    log.info(f"Total items loaded: {len(all_items)} from {files_loaded} files")
    return all_items


def build_synthesis_prompt(all_items, week_monday_str):
    """
    Build the Claude Sonnet synthesis prompt from all week's items.
    Carefully structured so Sonnet produces a usable weekly narrative.
    """
    # Prepare structured data for the prompt
    theme_counts = Counter(item.get("theme", "unknown") for item in all_items)
    top_themes = theme_counts.most_common(8)

    # Top items by score
    top_items = sorted(all_items, key=lambda x: x.get("relevance_score", 0), reverse=True)[:20]

    # All power quotes
    quotes = [
        (item.get("power_quote"), item.get("theme"), item.get("feed_name") or item.get("subreddit"))
        for item in all_items if item.get("power_quote") and item.get("relevance_score", 0) >= 7
    ]

    # All coaching items
    coaching_items = [i for i in all_items if i.get("coaching_flag")]

    # All statistics
    all_stats = []
    for item in all_items:
        for stat in item.get("key_statistics", []):
            if stat:
                all_stats.append(stat)

    # All LinkedIn hooks
    all_hooks = []
    for item in top_items[:10]:
        for hook in item.get("linkedin_hooks", []):
            if hook:
                all_hooks.append((hook, item.get("theme", "")))

    # Build compact data summary for the prompt
    themes_text = "\n".join(f"  - {t.replace('_',' ').title()}: {c} signals" for t, c in top_themes)
    quotes_text = "\n".join(f'  "{q[0]}" ({q[1]}, {q[2]})' for q in quotes[:15])
    stats_text = "\n".join(f"  • {s}" for s in all_stats[:20])
    hooks_text = "\n".join(f"  [{h[1]}] {h[0]}" for h in all_hooks[:12])

    top_signals_text = ""
    for item in top_items[:15]:
        title = item.get("title", "")[:80]
        score = item.get("relevance_score", 0)
        theme = (item.get("theme") or "").replace("_", " ").title()
        segment = (item.get("audience_segment") or "").replace("_", " ").title()
        summary = item.get("enrichment", {}).get("summary", "")[:200]
        top_signals_text += f"\n[{score}/10] [{theme}] [{segment}]\n{title}\n{summary}\n"

    coaching_text = ""
    for item in coaching_items[:10]:
        title = item.get("title", "")[:80]
        reason = item.get("enrichment", {}).get("coaching_reason", "")[:200]
        segment = (item.get("audience_segment") or "").replace("_", " ").title()
        coaching_text += f"\n[{segment}] {title}\n{reason}\n"

    prompt = f"""You are the lead intelligence analyst for B2Have, a Toronto-based career coaching firm serving the GTA/Ontario market.

You have just reviewed a full week of career intelligence signals ({len(all_items)} total items collected Mon-Sun, week of {week_monday_str}). Your job is to write a rich, insightful Weekly Narrative that a career coach will read every Sunday to plan their week.

This is NOT a summary — it's a synthesis. Find the story in the data. What matters? What surprised you? What should the coach do about it?

THE WEEK'S DATA:

THEME DISTRIBUTION:
{themes_text}

TOP SIGNALS (highest relevance):
{top_signals_text}

KEY STATISTICS EXTRACTED:
{stats_text}

REAL VOICES — POWER QUOTES:
{quotes_text}

COACHING OPPORTUNITIES FLAGGED:
{coaching_text}

LINKEDIN HOOKS GENERATED:
{hooks_text}

---

Write the Weekly Narrative in this exact structure. Be specific, insightful, and actionable. Reference real data from above. Minimum 1500 words total.

WEEKLY NARRATIVE — WEEK OF {week_monday_str}

## THE WEEK IN ONE SENTENCE
[One sentence capturing the dominant theme of this week's career landscape]

## WHAT DOMINATED THIS WEEK
[2-3 paragraphs analyzing the top 2-3 themes. What's the story? Why are these themes appearing together? What does it mean for your clients?]

## THE SIGNAL THAT MATTERED MOST
[Pick the single most important signal from the week. Why does it matter? What should a B2Have coach do with this insight TODAY?]

## WHAT CLIENTS ARE FEELING RIGHT NOW
[Based on the quotes and coaching flags, write 2 paragraphs about the emotional landscape of job seekers this week. What are they scared of? What's their language? What do they need to hear?]

## THE GTA / ONTARIO ANGLE
[How does this week's data apply specifically to the GTA market? Any Canada-specific signals? What's different for your Ontario clients vs US context?]

## CONTENT PRIORITIES FOR NEXT WEEK
[Based on this week's themes, name 3 specific content pieces (LinkedIn post, video, blog) B2Have should create next week. Give a title and 2-sentence rationale for each.]

## COACHING SESSION PREP
[5 coaching questions to keep in your back pocket this week based on what clients are actually struggling with right now]

## KEY STATISTICS TO CITE
[List the 5 most compelling statistics from this week that a coach could cite in content, consultations, or outreach]

## WEEK'S BEST LINKEDIN HOOKS
[The 5 strongest opening lines for LinkedIn posts from this week's data]

## LOOKING AHEAD
[Based on the patterns you see, what might dominate next week? Any signals that suggest something is building?]
"""
    return prompt


def write_rollup_to_drive(content, week_monday_str):
    """Write the weekly narrative to a new Google Doc."""
    from outputs.drive_writer import get_google_credentials, append_content_to_doc
    from googleapiclient.discovery import build

    doc_name = f"Career Intelligence — Weekly Narrative — Week of {week_monday_str}"
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    creds = get_google_credentials()
    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)

    # Check if already exists
    query = (f"name='{doc_name}' and '{folder_id}' in parents "
             f"and mimeType='application/vnd.google-apps.document' and trashed=false")
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])

    if files:
        doc_id = files[0]["id"]
        log.info(f"Found existing rollup doc: {doc_name}")
    else:
        doc = docs_service.documents().create(body={"title": doc_name}).execute()
        doc_id = doc.get("documentId")
        drive_service.files().update(
            fileId=doc_id, addParents=folder_id, removeParents="root", fields="id, parents"
        ).execute()
        log.info(f"Created new rollup doc: {doc_name}")

    append_content_to_doc(docs_service, doc_id, content)
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    log.info(f"✓ Weekly Narrative written to: {doc_url}")
    return doc_id, doc_url


def run_weekly_rollup(week_monday_str=None):
    """Main rollup function."""
    if week_monday_str is None:
        week_monday_str = get_current_week_monday()

    log.info(DIVIDER)
    log.info(f"WEEKLY ROLLUP — Week of {week_monday_str}")
    log.info(DIVIDER)

    # Load all this week's enriched items
    all_items = load_week_enriched_items(week_monday_str)

    if not all_items:
        log.error("No enriched items found for this week. Run daily pipeline first.")
        return None, None

    log.info(f"Synthesizing {len(all_items)} items with Claude Sonnet...")

    # Build synthesis prompt
    prompt = build_synthesis_prompt(all_items, week_monday_str)

    # Call Claude Sonnet for synthesis (smarter than Haiku — better narratives)
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    narrative = response.content[0].text
    log.info(f"Narrative generated: {len(narrative)} characters")

    # Add header
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    full_doc = f"""{DIVIDER}
CAREER INTELLIGENCE — WEEKLY NARRATIVE
Week of {week_monday_str} | B2Have Career Coaching | GTA / Toronto
Generated by Claude Sonnet | {now_str}
Total signals analyzed: {len(all_items)}
{DIVIDER}

{narrative}

{DIVIDER}
END OF WEEKLY NARRATIVE — Week of {week_monday_str}
{DIVIDER}
"""

    # Write to Drive
    doc_id, doc_url = write_rollup_to_drive(full_doc, week_monday_str)

    log.info(DIVIDER)
    log.info(f"✓ Weekly Rollup Complete")
    log.info(f"📄 {doc_url}")
    log.info(DIVIDER)

    return doc_id, doc_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B2Have Weekly Intelligence Rollup")
    parser.add_argument("--week", type=str, default=None,
                        help="Monday date of week to roll up (YYYY-MM-DD). Defaults to current week.")
    args = parser.parse_args()
    run_weekly_rollup(args.week)
