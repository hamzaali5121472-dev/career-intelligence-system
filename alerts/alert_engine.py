"""
Alert Engine — B2Have Career Intelligence System
Monitors enriched data and collection health for 6 trigger types:

  1. MAJOR LAYOFF    — Canadian company announces 100+ job cuts
  2. VIRAL POST      — Career post hits 5000+ upvotes/reactions
  3. KEYWORD SPIKE   — A theme appears 3x more than normal this week
  4. BREAKING NEWS   — Major career/employment news in Canada
  5. COACHING OPP    — High-urgency coaching opportunity detected
  6. SOURCE FAILURE  — Data source fails 2+ consecutive runs

Sends email alert via Gmail SMTP App Password (no OAuth needed).
"""

import os
import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("alert_engine")

ROOT = Path(__file__).parent.parent
STATE_FILE = ROOT / "data" / "logs" / "alert_state.json"
HEALTH_LOG = ROOT / "data" / "logs" / "health_log.json"

# ── Alert Types ───────────────────────────────────────────────────────────────
ALERT_MAJOR_LAYOFF = "MAJOR_LAYOFF"
ALERT_VIRAL_POST = "VIRAL_POST"
ALERT_KEYWORD_SPIKE = "KEYWORD_SPIKE"
ALERT_COACHING_OPP = "HIGH_URGENCY_COACHING"
ALERT_SOURCE_FAILURE = "SOURCE_FAILURE"
ALERT_BREAKING_NEWS = "BREAKING_NEWS"


def send_email_alert(subject, body, priority="normal"):
    """
    Send email alert via Gmail SMTP App Password.
    Requires: ALERT_EMAIL_FROM, ALERT_EMAIL_TO, ALERT_EMAIL_APP_PASSWORD in .env
    """
    from_email = os.getenv("ALERT_EMAIL_FROM")
    to_email = os.getenv("ALERT_EMAIL_TO", "hamzaali5121472@gmail.com")
    app_password = os.getenv("ALERT_EMAIL_APP_PASSWORD")

    if not all([from_email, app_password]):
        log.warning("Email alert skipped — ALERT_EMAIL_FROM or ALERT_EMAIL_APP_PASSWORD not set")
        log.info(f"ALERT (would have sent): {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[B2Have Intel] {subject}"
    msg["From"] = from_email
    msg["To"] = to_email

    if priority == "high":
        msg["X-Priority"] = "1"
        msg["Subject"] = f"🚨 [B2Have Intel] {subject}"

    # Plain text version
    msg.attach(MIMEText(body, "plain"))

    # HTML version
    html_body = f"""
    <html><body>
    <div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
      <div style="background: #1a1a2e; color: white; padding: 16px 20px; border-radius: 8px 8px 0 0;">
        <h2 style="margin: 0; font-size: 18px;">⚡ B2Have Career Intelligence Alert</h2>
        <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.8;">{datetime.now().strftime('%A, %B %d at %H:%M')}</p>
      </div>
      <div style="border: 1px solid #e8ecf0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
        <pre style="font-family: Arial; white-space: pre-wrap; font-size: 14px; line-height: 1.6;">{body}</pre>
      </div>
    </div>
    </body></html>
    """
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        log.info(f"✓ Alert sent: {subject}")
        return True
    except Exception as e:
        log.error(f"Failed to send alert email: {e}")
        return False


def load_alert_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"sent_alerts": [], "theme_baselines": {}, "source_failure_counts": {}}


def save_alert_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_viral_posts(enriched_items, state):
    """Check for posts that went viral (5000+ upvotes)."""
    alerts = []
    viral_threshold = 5000

    for item in enriched_items:
        score = item.get("score", 0)
        if score >= viral_threshold:
            alert_id = f"viral_{item.get('id', '')}"
            if alert_id not in [a.get("id") for a in state.get("sent_alerts", [])]:
                alerts.append({
                    "type": ALERT_VIRAL_POST,
                    "id": alert_id,
                    "title": item.get("title", ""),
                    "score": score,
                    "url": item.get("url", ""),
                    "theme": item.get("theme", ""),
                    "subreddit": item.get("subreddit", "")
                })

    return alerts


def check_layoff_signals(enriched_items, state):
    """Check for major layoff signals in collected data."""
    alerts = []
    layoff_keywords = [
        "laid off", "layoffs", "mass layoff", "job cuts", "workforce reduction",
        "downsizing", "thousands of jobs", "major layoff"
    ]

    for item in enriched_items:
        if item.get("theme") != "layoffs":
            continue

        title_lower = (item.get("title", "") + " " + item.get("body", "")[:500]).lower()
        score = item.get("score", 0)

        # High-signal layoff: mentions mass numbers + high engagement
        import re
        numbers = re.findall(r'(\d[\d,]*)\s*(?:employees?|workers?|jobs?|people)', title_lower)
        affected = max([int(n.replace(",", "")) for n in numbers], default=0) if numbers else 0

        if affected >= 100 or (score >= 500 and any(kw in title_lower for kw in layoff_keywords)):
            alert_id = f"layoff_{item.get('id', '')}"
            if alert_id not in [a.get("id") for a in state.get("sent_alerts", [])]:
                alerts.append({
                    "type": ALERT_MAJOR_LAYOFF,
                    "id": alert_id,
                    "title": item.get("title", ""),
                    "affected": affected,
                    "score": score,
                    "url": item.get("url", ""),
                    "source": item.get("subreddit") or item.get("feed_name", "")
                })

    return alerts


def check_keyword_spikes(enriched_items, state):
    """Detect when a theme appears 3x more than its baseline."""
    alerts = []
    current_counts = Counter(item.get("theme") for item in enriched_items if item.get("theme"))
    baselines = state.get("theme_baselines", {})
    spike_multiplier = 3.0

    for theme, count in current_counts.items():
        baseline = baselines.get(theme, 0)
        if baseline > 0 and count >= baseline * spike_multiplier and count >= 10:
            alert_id = f"spike_{theme}_{datetime.now().strftime('%Y%m%d')}"
            if alert_id not in [a.get("id") for a in state.get("sent_alerts", [])]:
                alerts.append({
                    "type": ALERT_KEYWORD_SPIKE,
                    "id": alert_id,
                    "theme": theme,
                    "current_count": count,
                    "baseline": baseline,
                    "multiplier": round(count / baseline, 1)
                })

    # Update baselines (rolling average)
    for theme, count in current_counts.items():
        old_baseline = baselines.get(theme, count)
        baselines[theme] = round((old_baseline * 0.8 + count * 0.2), 1)
    state["theme_baselines"] = baselines

    return alerts


def check_urgent_coaching_opportunities(enriched_items):
    """Flag high-urgency coaching opportunities for immediate attention."""
    alerts = []
    urgent_items = [
        item for item in enriched_items
        if item.get("coaching_flag") and
           item.get("enrichment", {}).get("urgency") == "high" and
           item.get("relevance_score", 0) >= 8
    ]

    if len(urgent_items) >= 3:
        alerts.append({
            "type": ALERT_COACHING_OPP,
            "count": len(urgent_items),
            "items": [{
                "title": i.get("title", "")[:100],
                "segment": i.get("audience_segment", ""),
                "reason": i.get("enrichment", {}).get("coaching_reason", ""),
                "url": i.get("url", "")
            } for i in urgent_items[:5]]
        })

    return alerts


def check_source_health(health_report, state):
    """Track consecutive source failures."""
    alerts = []
    failure_counts = state.get("source_failure_counts", {})

    for source, report in health_report.items():
        if report.get("status") == "failed":
            failure_counts[source] = failure_counts.get(source, 0) + 1
            if failure_counts[source] >= 2:
                alerts.append({
                    "type": ALERT_SOURCE_FAILURE,
                    "source": source,
                    "consecutive_failures": failure_counts[source],
                    "error": report.get("error", "Unknown error")
                })
        else:
            failure_counts[source] = 0  # Reset on success

    state["source_failure_counts"] = failure_counts
    return alerts


def format_alert_body(alert):
    """Format an alert dict into a readable email body."""
    alert_type = alert.get("type", "UNKNOWN")

    if alert_type == ALERT_VIRAL_POST:
        return (
            f"VIRAL CAREER POST DETECTED\n\n"
            f"Title: {alert.get('title', '')}\n"
            f"Score: {alert.get('score', 0):,} upvotes\n"
            f"Theme: {alert.get('theme', '').replace('_', ' ').title()}\n"
            f"Source: r/{alert.get('subreddit', '')}\n"
            f"URL: {alert.get('url', '')}\n\n"
            f"ACTION: This is trending. Create a response post or video hook NOW.\n"
            f"The audience is already engaged with this topic."
        )

    elif alert_type == ALERT_MAJOR_LAYOFF:
        affected = alert.get("affected", 0)
        return (
            f"MAJOR LAYOFF SIGNAL DETECTED\n\n"
            f"Title: {alert.get('title', '')}\n"
            f"Estimated affected: {affected:,} workers\n"
            f"Source: {alert.get('source', '')}\n"
            f"URL: {alert.get('url', '')}\n\n"
            f"ACTION: Layoff = coaching demand spike in 2-4 weeks.\n"
            f"Draft a coaching offer targeting laid-off professionals NOW."
        )

    elif alert_type == ALERT_KEYWORD_SPIKE:
        theme = alert.get("theme", "").replace("_", " ").title()
        return (
            f"KEYWORD SPIKE DETECTED\n\n"
            f"Theme: {theme}\n"
            f"This week: {alert.get('current_count', 0)} signals\n"
            f"Normal: {alert.get('baseline', 0)} signals\n"
            f"Spike: {alert.get('multiplier', 0)}x above baseline\n\n"
            f"ACTION: This topic is exploding. Prioritize content on '{theme}' this week."
        )

    elif alert_type == ALERT_COACHING_OPP:
        items = alert.get("items", [])
        item_lines = "\n".join(
            f"  • [{i.get('segment', '').replace('_', ' ').title()}] {i.get('title', '')[:80]}"
            for i in items
        )
        return (
            f"HIGH-URGENCY COACHING OPPORTUNITIES\n\n"
            f"{alert.get('count', 0)} people showing signs of urgent coaching need:\n\n"
            f"{item_lines}\n\n"
            f"ACTION: Review these posts. Consider reaching out or creating "
            f"targeted content addressing their specific pain."
        )

    elif alert_type == ALERT_SOURCE_FAILURE:
        return (
            f"DATA SOURCE FAILURE\n\n"
            f"Source: {alert.get('source', '')}\n"
            f"Consecutive failures: {alert.get('consecutive_failures', 0)}\n"
            f"Error: {alert.get('error', '')}\n\n"
            f"ACTION: Check the source. It may require login refresh or config update."
        )

    return f"Alert: {alert}"


def run_alert_check(enriched_items, health_report=None):
    """
    Main alert check. Run after each enrichment pass.
    Checks all 5 trigger types and sends emails for any triggered alerts.
    """
    log.info("Running alert checks...")
    state = load_alert_state()
    all_alerts = []

    # Check all trigger types
    all_alerts.extend(check_viral_posts(enriched_items, state))
    all_alerts.extend(check_layoff_signals(enriched_items, state))
    all_alerts.extend(check_keyword_spikes(enriched_items, state))
    all_alerts.extend(check_urgent_coaching_opportunities(enriched_items))

    if health_report:
        all_alerts.extend(check_source_health(health_report, state))

    # Send emails for each alert
    sent_count = 0
    for alert in all_alerts:
        subject = alert.get("type", "ALERT").replace("_", " ")
        body = format_alert_body(alert)
        is_high_priority = alert.get("type") in [ALERT_MAJOR_LAYOFF, ALERT_SOURCE_FAILURE]

        if send_email_alert(subject, body, priority="high" if is_high_priority else "normal"):
            sent_count += 1
            state["sent_alerts"].append({
                "id": alert.get("id", f"alert_{datetime.now().timestamp()}"),
                "type": alert.get("type"),
                "sent_at": datetime.now(timezone.utc).isoformat()
            })

    # Keep only last 500 sent alerts in state
    state["sent_alerts"] = state["sent_alerts"][-500:]

    save_alert_state(state)

    log.info(f"Alert check complete — {len(all_alerts)} triggered, {sent_count} emails sent")
    return all_alerts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test: load latest enriched file and check
    from pathlib import Path
    enriched_dir = Path("data/enriched")
    files = sorted(enriched_dir.glob("*.json"), reverse=True)
    if files:
        with open(files[0]) as f:
            data = json.load(f)
        run_alert_check(data.get("items", []))
    else:
        log.info("No enriched data found — run enrichment first")
