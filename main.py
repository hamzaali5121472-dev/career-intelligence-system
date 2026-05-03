"""
Main Orchestrator — B2Have Career Intelligence System
Runs the full pipeline in sequence:
  1. Collect (Reddit + RSS + Job Bank)
  2. Enrich (Claude Haiku AI tagging)
  3. Alert check (6 trigger types)
  4. Write to Google Drive (weekly doc)

Usage:
  python main.py                    # Full pipeline run
  python main.py --collect-only     # Just collect raw data
  python main.py --enrich-only      # Just enrich existing raw data
  python main.py --write-only       # Just write enriched data to Drive
  python main.py --test             # Test all connections, don't process
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging Setup ─────────────────────────────────────────────────────────────
Path("data/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/pipeline.log", mode="a")
    ]
)
log = logging.getLogger("main")


def run_pipeline(args):
    """Execute the full intelligence pipeline."""
    start_time = datetime.now(timezone.utc)

    log.info("=" * 70)
    log.info("B2HAVE CAREER INTELLIGENCE SYSTEM — PIPELINE START")
    log.info(f"Run time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    log.info("=" * 70)

    all_health_reports = {}
    collected_files = []
    enriched_file = None

    # ── STEP 1: COLLECTION ────────────────────────────────────────────────────
    if not args.enrich_only and not args.write_only:
        log.info("\n[STEP 1/4] COLLECTION")

        # Reddit
        if not args.skip_reddit:
            log.info("▸ Starting Reddit collection...")
            try:
                from collectors.reddit_collector import run_collection as reddit_collect
                reddit_file, reddit_health = reddit_collect()
                collected_files.append(reddit_file)
                all_health_reports.update(reddit_health)
                log.info(f"  ✓ Reddit: {reddit_file}")
            except Exception as e:
                log.error(f"  ✗ Reddit collection failed: {e}")
                all_health_reports["reddit_overall"] = {"status": "failed", "error": str(e)}

        # RSS Feeds
        if not args.skip_rss:
            log.info("▸ Starting RSS collection...")
            try:
                from collectors.rss_collector import run_collection as rss_collect
                rss_file, rss_health = rss_collect()
                collected_files.append(rss_file)
                all_health_reports.update(rss_health)
                log.info(f"  ✓ RSS: {rss_file}")
            except Exception as e:
                log.error(f"  ✗ RSS collection failed: {e}")
                all_health_reports["rss_overall"] = {"status": "failed", "error": str(e)}

        # Job Bank (weekly only — skip if not Monday)
        day_of_week = datetime.now().weekday()
        if day_of_week == 0 or args.force_job_bank:
            log.info("▸ Starting Job Bank Canada collection (weekly)...")
            try:
                from collectors.job_bank_collector import run_collection as jb_collect
                jb_file = jb_collect()
                collected_files.append(jb_file)
                log.info(f"  ✓ Job Bank: {jb_file}")
            except Exception as e:
                log.error(f"  ✗ Job Bank collection failed: {e}")

        if args.collect_only:
            log.info(f"\nCollection-only run complete. Files: {collected_files}")
            return

    # ── STEP 2: ENRICHMENT ────────────────────────────────────────────────────
    if not args.collect_only and not args.write_only:
        log.info("\n[STEP 2/4] AI ENRICHMENT (Claude Haiku)")
        try:
            from enrichment.claude_enricher import run_enrichment
            enriched_file, enrichment_meta = run_enrichment(since_hours=25)
            if enriched_file:
                log.info(f"  ✓ Enrichment complete: {enrichment_meta.get('enriched_items', 0)} items")
            else:
                log.info("  ℹ No new items to enrich")
        except Exception as e:
            log.error(f"  ✗ Enrichment failed: {e}")
            enriched_file = None

    # ── STEP 3: ALERT CHECK ───────────────────────────────────────────────────
    log.info("\n[STEP 3/4] ALERT CHECK")
    if enriched_file:
        try:
            with open(enriched_file) as f:
                enriched_data = json.load(f)
            enriched_items = enriched_data.get("items", [])

            from alerts.alert_engine import run_alert_check
            alerts = run_alert_check(enriched_items, all_health_reports)
            log.info(f"  ✓ Alert check complete — {len(alerts)} alerts triggered")
        except Exception as e:
            log.error(f"  ✗ Alert check failed: {e}")
    else:
        log.info("  ℹ Skipped — no enriched data this run")

    # ── STEP 4: WRITE TO GOOGLE DRIVE ────────────────────────────────────────
    if not args.collect_only and not args.enrich_only:
        log.info("\n[STEP 4/4] WRITE TO GOOGLE DRIVE")
        if enriched_file:
            try:
                with open(enriched_file) as f:
                    enriched_data = json.load(f)
                enriched_items = enriched_data.get("items", [])

                if enriched_items:
                    from outputs.weekly_rotator import get_current_week_info, register_week_doc
                    from outputs.doc_formatter import format_weekly_doc
                    from outputs.drive_writer import write_weekly_intelligence

                    week_info = get_current_week_info()
                    week_label = week_info["week_label"]
                    week_start = week_info["week_start"]
                    week_end = week_info["week_end"]

                    formatted_content = format_weekly_doc(
                        enriched_items, week_label, week_start, week_end
                    )

                    doc_id, doc_url = write_weekly_intelligence(
                        enriched_items, formatted_content, week_label
                    )

                    register_week_doc(doc_id, doc_url, week_label)

                    log.info(f"  ✓ Written to Google Drive")
                    log.info(f"  📄 Doc URL: {doc_url}")
                else:
                    log.info("  ℹ No enriched items to write this run")

            except Exception as e:
                log.error(f"  ✗ Drive write failed: {e}")
                log.error("  Check GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_DRIVE_FOLDER_ID in .env")
        else:
            log.info("  ℹ Skipped — no enriched data this run")

    # ── PIPELINE SUMMARY ─────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    log.info("\n" + "=" * 70)
    log.info("PIPELINE COMPLETE")
    log.info(f"Total runtime: {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    log.info(f"Files collected: {len(collected_files)}")

    failed_sources = [k for k, v in all_health_reports.items() if v.get("status") == "failed"]
    if failed_sources:
        log.warning(f"Failed sources: {', '.join(failed_sources)}")
    else:
        log.info("All sources healthy ✓")

    log.info("=" * 70)


def test_connections():
    """Test all API connections without collecting data."""
    log.info("Testing connections...")

    # Test Reddit
    try:
        import praw
        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "test/1.0")
        )
        me = reddit.user.me()
        log.info(f"  ✓ Reddit: connected as {me}")
    except Exception as e:
        log.error(f"  ✗ Reddit: {e}")

    # Test Anthropic
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        log.info(f"  ✓ Anthropic API: connected (claude-haiku-4-5)")
    except Exception as e:
        log.error(f"  ✗ Anthropic: {e}")

    # Test Google Drive
    try:
        from outputs.drive_writer import get_google_credentials
        from googleapiclient.discovery import build
        creds = get_google_credentials()
        service = build("drive", "v3", credentials=creds)
        about = service.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        log.info(f"  ✓ Google Drive: connected as {email}")
    except Exception as e:
        log.error(f"  ✗ Google Drive: {e}")

    log.info("Connection test complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B2Have Career Intelligence Pipeline")
    parser.add_argument("--collect-only", action="store_true", help="Only run collection")
    parser.add_argument("--enrich-only", action="store_true", help="Only run enrichment")
    parser.add_argument("--write-only", action="store_true", help="Only write to Drive")
    parser.add_argument("--skip-reddit", action="store_true", help="Skip Reddit collection")
    parser.add_argument("--skip-rss", action="store_true", help="Skip RSS collection")
    parser.add_argument("--force-job-bank", action="store_true", help="Force Job Bank run")
    parser.add_argument("--test", action="store_true", help="Test connections only")

    args = parser.parse_args()

    if args.test:
        test_connections()
    else:
        run_pipeline(args)
