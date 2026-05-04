"""
Deduplicator — B2Have Career Intelligence System
Tracks content hashes across all sources and all runs.
Prevents the same post/article from being enriched or stored twice.

Uses a 7-day rolling window — hashes older than 7 days are forgotten,
so next week's pipeline always processes articles fresh.

Set FORCE_REPROCESS=true in .env to bypass deduplication for testing.
"""

import json
import hashlib
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("deduplicator")

ROOT = Path(__file__).parent.parent
HASH_STORE = ROOT / "data" / "logs" / "seen_hashes.json"

# How long to remember a hash before allowing re-processing
DEDUP_WINDOW_DAYS = 7


def load_seen_hashes():
    """
    Load the set of seen content hashes from the last DEDUP_WINDOW_DAYS days.
    Automatically expires old hashes so next week's pipeline starts fresh.
    """
    if not HASH_STORE.exists():
        return {}

    try:
        with open(HASH_STORE, encoding="utf-8") as f:
            data = json.load(f)

        # Support both old format (list of strings) and new format (dict with timestamps)
        raw = data.get("hashes", {})

        if isinstance(raw, list):
            # Old format: treat as current hashes with unknown date (keep them)
            return {h: datetime.now(timezone.utc).isoformat() for h in raw}

        # New format: dict of {hash: iso_timestamp}
        cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)
        active = {}
        expired = 0
        for h, ts_str in raw.items():
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff:
                    active[h] = ts_str
                else:
                    expired += 1
            except Exception:
                active[h] = ts_str  # Keep if timestamp is unparseable

        if expired > 0:
            log.info(f"Deduplicator: expired {expired} old hashes (>{DEDUP_WINDOW_DAYS} days)")

        return active

    except Exception as e:
        log.warning(f"Could not load seen_hashes.json: {e} — starting fresh")
        return {}


def save_seen_hashes(hash_dict):
    """Persist the seen hash dict to disk."""
    HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(HASH_STORE, "w", encoding="utf-8") as f:
        json.dump({
            "hashes": hash_dict,
            "count": len(hash_dict),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "window_days": DEDUP_WINDOW_DAYS
        }, f, indent=2)


def make_hash(text):
    """Generate a short SHA-256 fingerprint."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:20]


def filter_new_items(items, text_key="title"):
    """
    Filter a list of items to only those not seen in the last DEDUP_WINDOW_DAYS days.
    Updates and saves the seen hash store.

    Set FORCE_REPROCESS=true in .env to bypass deduplication entirely.
    Returns: (new_items, duplicate_count)
    """
    force = os.getenv("FORCE_REPROCESS", "false").lower() in ("true", "1", "yes")
    if force:
        log.info("FORCE_REPROCESS=true — skipping deduplication, processing all items")
        return items, 0

    seen = load_seen_hashes()
    new_items = []
    duplicate_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for item in items:
        # Use existing content_hash if present, otherwise generate one
        item_hash = item.get("content_hash") or make_hash(
            item.get(text_key, "") + item.get("url", "")
        )
        item["content_hash"] = item_hash

        if item_hash in seen:
            duplicate_count += 1
        else:
            seen[item_hash] = now_iso
            new_items.append(item)

    save_seen_hashes(seen)
    log.info(f"Deduplication: {len(new_items)} new, {duplicate_count} duplicates skipped "
             f"(window: {DEDUP_WINDOW_DAYS} days)")
    return new_items, duplicate_count
