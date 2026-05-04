"""
Daily Tracker — B2Have Career Intelligence System
Manages the daily doc lifecycle:
  - Each pipeline run produces one doc per day
  - Tracks which docs have been created (for weekly rollup to reference)
  - Returns today's date label and display string

Replaces weekly_rotator.py in the daily pipeline architecture.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("daily_tracker")
ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "logs" / "daily_state.json"


def get_today_info():
    """Return all date metadata needed by the daily pipeline."""
    now = datetime.now(timezone.utc)
    day_label = now.strftime("%Y-%m-%d")           # "2026-05-04"
    day_display = now.strftime("%A, %B %d, %Y")    # "Sunday, May 04, 2026"
    week_label = _get_week_label(now)              # "2026-04-28" (Monday of current week)

    return {
        "day_label": day_label,
        "day_display": day_display,
        "week_label": week_label,
        "is_sunday": now.weekday() == 6,
        "is_monday": now.weekday() == 0,
        "weekday": now.strftime("%A")
    }


def _get_week_label(date):
    """Return the Monday of the week containing date."""
    from datetime import timedelta
    monday = date - timedelta(days=date.weekday())
    return monday.strftime("%Y-%m-%d")


def load_daily_state():
    """Load persistent state tracking which docs have been created."""
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"days": {}}


def save_daily_state(state):
    """Save persistent state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def register_daily_doc(doc_id, doc_url, day_label):
    """Register a newly created/updated daily doc in state."""
    state = load_daily_state()

    if day_label not in state["days"]:
        state["days"][day_label] = {
            "doc_id": doc_id,
            "doc_url": doc_url,
            "day_label": day_label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "runs": 1
        }
    else:
        state["days"][day_label]["last_updated"] = datetime.now(timezone.utc).isoformat()
        state["days"][day_label]["doc_id"] = doc_id
        state["days"][day_label]["doc_url"] = doc_url
        state["days"][day_label]["runs"] = state["days"][day_label].get("runs", 0) + 1

    save_daily_state(state)
    return state


def get_doc_id_for_day(day_label):
    """Get the doc ID for a specific day, or None if not created yet."""
    state = load_daily_state()
    day_data = state["days"].get(day_label)
    return day_data.get("doc_id") if day_data else None


def get_docs_for_week(week_label):
    """
    Get all daily doc IDs and URLs for a given week (Mon-Sun).
    week_label = Monday's date string, e.g. "2026-04-28"
    Returns list of {day_label, doc_id, doc_url} dicts.
    """
    from datetime import timedelta
    state = load_daily_state()

    monday = datetime.strptime(week_label, "%Y-%m-%d")
    week_days = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    docs = []
    for day in week_days:
        if day in state["days"]:
            docs.append({
                "day_label": day,
                "doc_id": state["days"][day].get("doc_id"),
                "doc_url": state["days"][day].get("doc_url")
            })

    return docs


def get_recent_doc_ids(num_days=7):
    """Get doc IDs for the most recent N days (for NotebookLM)."""
    state = load_daily_state()
    days = sorted(state["days"].keys(), reverse=True)[:num_days]
    return [state["days"][d]["doc_id"] for d in days if "doc_id" in state["days"][d]]
