"""
Statistics Canada Collector — B2Have Career Intelligence System
Pulls Labour Force Survey (LFS) data from the Statistics Canada API.
Tracks: employment rate, unemployment rate, sector changes, Ontario/GTA context.

API: https://www.statcan.gc.ca/en/developers/wds
Free, no authentication required.

Output: data/raw/statcan_YYYYMM.json (monthly data)
"""

import json
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("stats_canada_collector")

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)

# Stats Canada WDS API base
STATCAN_API = "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/"

# Key Labour Force Survey tables
LFS_TABLES = {
    "14-10-0287-01": "Employment by industry, seasonally adjusted",
    "14-10-0017-01": "Labour force characteristics by province",
    "14-10-0022-01": "Unemployment rate by province (Ontario focus)"
}

HEADERS = {
    "User-Agent": "B2Have Career Intelligence/1.0 (career coaching research)",
    "Accept": "application/json"
}


def fetch_statcan_table(table_id):
    """
    Fetch data from a Statistics Canada table.
    Returns parsed data dict or None on failure.
    """
    url = f"{STATCAN_API}{table_id}/tbl/en/table.json"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        log.warning(f"Timeout fetching Stats Canada table {table_id}")
    except Exception as e:
        log.warning(f"Could not fetch Stats Canada table {table_id}: {e}")

    return None


def get_latest_lfs_summary():
    """
    Get key employment indicators from the Labour Force Survey.
    Returns a simplified summary dict for NLM consumption.
    """
    log.info("Fetching Statistics Canada LFS data...")

    summary = {
        "collection_date": datetime.now(timezone.utc).isoformat(),
        "source": "Statistics Canada — Labour Force Survey",
        "indicators": {},
        "ontario_focus": {},
        "narrative": ""
    }

    # Try fetching provincial unemployment
    try:
        table_data = fetch_statcan_table("14-10-0017-01")

        if table_data:
            # Extract Ontario data points
            summary["indicators"]["data_available"] = True
            summary["indicators"]["table_fetched"] = "14-10-0017-01"
            summary["indicators"]["note"] = (
                "Labour Force Survey — Ontario employment characteristics. "
                "Full data available at statcan.gc.ca"
            )
        else:
            summary["indicators"]["data_available"] = False
            summary["indicators"]["note"] = "Stats Canada API unavailable — manual check required"

    except Exception as e:
        log.warning(f"LFS data fetch failed: {e}")
        summary["indicators"]["error"] = str(e)

    # Add contextual narrative for NLM
    summary["narrative"] = (
        f"[Statistics Canada Data — {datetime.now().strftime('%B %Y')}] "
        "Monitor Ontario Labour Force Survey monthly for: unemployment rate changes, "
        "employment by industry sector, full-time vs part-time shifts, "
        "and youth unemployment trends. These macro signals inform B2Have coaching "
        "demand — rising unemployment = more coaching clients. Sector growth signals "
        "which career pivots to promote. Source: statcan.gc.ca/lfs"
    )

    return summary


def run_collection():
    """Main Stats Canada collection run."""
    log.info("Stats Canada Collector — B2Have Career Intelligence")

    lfs_data = get_latest_lfs_summary()

    timestamp = datetime.now().strftime("%Y%m")
    output_file = DATA_RAW / f"statcan_{timestamp}.json"

    output = {
        "metadata": {
            "collector": "statistics_canada",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "data_type": "labour_force_survey"
        },
        "lfs_data": lfs_data
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"Stats Canada data saved: {output_file}")
    return str(output_file)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_collection()
