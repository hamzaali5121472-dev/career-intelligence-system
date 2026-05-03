"""
Weekly Rotator — B2Have Career Intelligence System
Manages the weekly doc lifecycle:
  - Every Monday: creates new week's doc
  - Archives previous week with summary stats
  - Returns current week label and date range

Also manages the 4-notebook NLM architecture by tracking which docs
belong to which notebook (Live Pulse rotates weekly, others accumulate).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("weekly_rotator")
ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "logs" / "weekly_state.json"


def get_week_label(date=None):
    """
    Return the Monday of the current week as a label string.
    e.g., "2025-01-13"
    """
    if date is None:
        date = datetime.now(timezone.utc)

    # Get Monday of current week
    monday = date - timedelta(days=date.weekday())
    return monday.strftime("%Y-%m-%d")


def get_week_range(date=None):
    """Return (week_start_str, week_end_str) for the current week."""
    if date is None:
        date = datetime.now(timezone.utc)
    monday = date - timedelta(days=date.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_current_week_info():
    """Return all week metadata needed by the pipeline."""
    now = datetime.now(timezone.utc)
    week_label = get_week_label(now)
    week_start, week_end = get_week_range(now)
    week_number = now.isocalendar()[1]
    year = now.year

    return {
        "week_label": week_label,
        "week_start": week_start,
        "week_end": week_end,
        "week_number": week_number,
        "year": year,
        "is_monday": now.weekday() == 0
    }


def load_weekly_state():
    """Load persistent state tracking which docs have been created."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"weeks": {}, "notebooks": {}}


def save_weekly_state(state):
    """Save persistent state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def register_week_doc(doc_id, doc_url, week_label):
    """Register a newly created/updated weekly doc in state."""
    state = load_weekly_state()

    if week_label not in state["weeks"]:
        state["weeks"][week_label] = {
            "doc_id": doc_id,
            "doc_url": doc_url,
            "week_label": week_label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "items_written": 0,
            "runs": 0
        }
    else:
        state["weeks"][week_label]["last_updated"] = datetime.now(timezone.utc).isoformat()
        state["weeks"][week_label]["runs"] = state["weeks"][week_label].get("runs", 0) + 1

    save_weekly_state(state)
    return state


def get_doc_id_for_week(week_label):
    """Get the doc ID for a specific week, or None if not created yet."""
    state = load_weekly_state()
    week_data = state["weeks"].get(week_label)
    return week_data.get("doc_id") if week_data else None


def get_recent_doc_ids(num_weeks=4):
    """Get doc IDs for the most recent N weeks (for NLM Live Pulse notebook)."""
    state = load_weekly_state()
    weeks = sorted(state["weeks"].keys(), reverse=True)[:num_weeks]
    return [state["weeks"][w]["doc_id"] for w in weeks if "doc_id" in state["weeks"][w]]
