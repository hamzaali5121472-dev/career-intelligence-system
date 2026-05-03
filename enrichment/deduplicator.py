"""
Deduplicator — B2Have Career Intelligence System
Tracks content hashes across all sources and all runs.
Prevents the same post/article from being enriched or stored twice.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger("deduplicator")

ROOT = Path(__file__).parent.parent
HASH_STORE = ROOT / "data" / "logs" / "seen_hashes.json"


def load_seen_hashes():
    """Load the persistent set of seen content hashes."""
    if HASH_STORE.exists():
        with open(HASH_STORE) as f:
            data = json.load(f)
            return set(data.get("hashes", []))
    return set()


def save_seen_hashes(hashes):
    """Persist the seen hash set to disk."""
    HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
    with open(HASH_STORE, "w") as f:
        json.dump({
            "hashes": list(hashes),
            "count": len(hashes),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)


def make_hash(text):
    """Generate a short SHA-256 fingerprint."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:20]


def filter_new_items(items, text_key="title"):
    """
    Filter a list of items to only those not seen before.
    Updates and saves the seen hash set.
    Returns: (new_items, duplicate_count)
    """
    seen = load_seen_hashes()
    new_items = []
    duplicate_count = 0

    for item in items:
        # Use existing content_hash if present, otherwise generate one
        item_hash = item.get("content_hash") or make_hash(
            item.get(text_key, "") + item.get("url", "")
        )
        item["content_hash"] = item_hash

        if item_hash in seen:
            duplicate_count += 1
        else:
            seen.add(item_hash)
            new_items.append(item)

    save_seen_hashes(seen)
    log.info(f"Deduplication: {len(new_items)} new, {duplicate_count} duplicates skipped")
    return new_items, duplicate_count
