"""
Job Bank Canada Collector — B2Have Career Intelligence System
Collects Canadian job market data from the Government of Canada Job Bank API.
Focuses on GTA/Ontario market: hiring trends, top sectors, emerging roles.

API docs: https://www.jobbank.gc.ca/jobsearch/
Free — no authentication required for basic search, API key for higher limits.

Output: JSON file per run → data/raw/jobbank_YYYYMMDD.json
"""

import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("job_bank_collector")

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_RAW.mkdir(parents=True, exist_ok=True)

JOB_BANK_BASE = "https://www.jobbank.gc.ca/jobsearch/jobposting"
JOB_BANK_SEARCH = "https://www.jobbank.gc.ca/jobsearch/jobsearch"

# GTA location codes for Job Bank API
GTA_LOCATIONS = {
    "toronto": "7297",
    "mississauga": "7280",
    "brampton": "7225",
    "markham": "7278",
    "vaughan": "7302",
    "oakville": "7282"
}

# Job categories to track (NOC codes for career coaching relevance)
TRACKED_CATEGORIES = [
    "business",
    "finance",
    "sales",
    "marketing",
    "human_resources",
    "information_technology",
    "management",
    "education",
    "healthcare"
]

HEADERS = {
    "User-Agent": "B2Have Career Intelligence/1.0 (research@b2have.ca)",
    "Accept": "application/json"
}


def search_job_bank(location_code, keywords, limit=50):
    """
    Search Job Bank for postings. Returns list of job posting summaries.
    Uses the public search API — no auth required.
    """
    params = {
        "searchstring": keywords,
        "locationstring": "",
        "locationid": location_code,
        "noc": "",
        "sort": "M",  # Most recent
        "action": "search",
        "button.submit": "Search",
        "lang": "en",
        "tp": limit
    }

    try:
        response = requests.get(
            JOB_BANK_SEARCH,
            params=params,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

        # Job Bank returns HTML — parse for job counts and trends
        # This approach extracts aggregate data rather than individual listings
        content = response.text

        # Extract job count from page
        import re
        count_match = re.search(r'(\d[\d,]*)\s+jobs?\s+found', content, re.IGNORECASE)
        job_count = 0
        if count_match:
            job_count = int(count_match.group(1).replace(",", ""))

        return {
            "location": location_code,
            "keywords": keywords,
            "job_count": job_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        log.warning(f"Job Bank search failed for {keywords} in {location_code}: {e}")
        return {"location": location_code, "keywords": keywords, "job_count": 0, "error": str(e)}


def get_gta_market_overview():
    """
    Get high-level GTA job market data.
    Searches multiple category/keyword combinations to build trend picture.
    """
    log.info("Collecting GTA job market overview from Job Bank Canada...")

    market_data = {
        "collection_date": datetime.now(timezone.utc).isoformat(),
        "location_breakdown": {},
        "category_breakdown": {},
        "trending_keywords": [],
        "source": "job_bank_canada"
    }

    career_keywords = [
        ("general", "jobs"),
        ("tech", "software developer"),
        ("hr", "human resources"),
        ("marketing", "marketing manager"),
        ("finance", "financial analyst"),
        ("management", "project manager"),
        ("sales", "sales representative"),
        ("healthcare", "registered nurse"),
        ("education", "teacher")
    ]

    toronto_code = GTA_LOCATIONS["toronto"]

    for category, keyword in career_keywords:
        result = search_job_bank(toronto_code, keyword, limit=100)
        market_data["category_breakdown"][category] = {
            "keyword": keyword,
            "gta_postings": result.get("job_count", 0),
            "timestamp": result.get("timestamp")
        }
        log.info(f"  {category}: {result.get('job_count', 0)} postings")
        time.sleep(2)  # Polite delay

    # Location breakdown (Toronto vs suburbs)
    for location_name, location_code in list(GTA_LOCATIONS.items())[:3]:
        result = search_job_bank(location_code, "jobs", limit=100)
        market_data["location_breakdown"][location_name] = result.get("job_count", 0)
        time.sleep(1)

    return market_data


def run_collection():
    """Main collection run for Job Bank data."""
    log.info("Job Bank Canada Collector — B2Have Career Intelligence")

    market_data = get_gta_market_overview()

    # Save output
    timestamp = datetime.now().strftime("%Y%m%d")
    output_file = DATA_RAW / f"jobbank_{timestamp}.json"

    output = {
        "metadata": {
            "collector": "job_bank_canada",
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "coverage": "GTA/Ontario"
        },
        "market_data": market_data
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"Job Bank data saved: {output_file}")
    return str(output_file)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_collection()
