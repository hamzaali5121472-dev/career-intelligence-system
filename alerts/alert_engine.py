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


SEGMENT_COLORS = {
    "mid_career_pivot":   "#2563eb",  # blue
    "senior_executive":   "#7c3aed",  # purple
    "new_graduate":       "#059669",  # green
    "career_returner":    "#d97706",  # amber
    "immigrant_professional": "#dc2626",  # red
    "entrepreneur":       "#0891b2",  # cyan
}

THEME_EMOJIS = {
    "ai_replacing_jobs": "🤖", "layoffs": "📉", "mental_health_burnout": "🔥",
    "remote_vs_office": "🏠", "salary_negotiation": "💰", "interview_anxiety": "😰",
    "ats_rejection": "🚫", "overqualified_age_bias": "⏳", "career_pivot": "🔄",
    "job_search_strategy": "🎯", "linkedin_personal_brand": "📢",
    "networking": "🤝", "resume_cover_letter": "📄", "work_life_balance": "⚖️",
    "workplace_culture_toxicity": "☠️", "immigration_work_permit": "🌍",
    "entrepreneurship": "🚀", "skill_upskilling": "📚",
}


def _segment_badge(segment):
    """Return an HTML badge for an audience segment."""
    label = segment.replace("_", " ").title() if segment else "General"
    color = SEGMENT_COLORS.get(segment, "#64748b")
    return (f'<span style="background:{color};color:white;padding:2px 8px;'
            f'border-radius:12px;font-size:11px;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.5px">{label}</span>')


def _theme_badge(theme):
    """Return a theme label with emoji."""
    emoji = THEME_EMOJIS.get(theme, "📌")
    label = theme.replace("_", " ").title() if theme else "Career"
    return f"{emoji} {label}"


def send_email_alert(subject, plain_body, html_body=None, priority="normal"):
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
    if priority == "high":
        msg["Subject"] = f"🚨 [B2Have Intel] {subject}"
        msg["X-Priority"] = "1"
    else:
        msg["Subject"] = f"[B2Have Intel] {subject}"
    msg["From"] = from_email
    msg["To"] = to_email

    msg.attach(MIMEText(plain_body, "plain"))

    if html_body:
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
           item.get("relevance_score", 0) >= 6
    ]

    if len(urgent_items) >= 2:
        alerts.append({
            "type": ALERT_COACHING_OPP,
            "count": len(urgent_items),
            "items": [{
                "title": i.get("title", ""),
                "segment": i.get("audience_segment", ""),
                "reason": i.get("enrichment", {}).get("coaching_reason", ""),
                "quote": i.get("power_quote", ""),
                "url": i.get("url", ""),
                "theme": i.get("theme", "")
            } for i in urgent_items[:6]]
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
    """
    Format an alert dict. Returns (plain_text, html_text) tuple.
    """
    alert_type = alert.get("type", "UNKNOWN")
    date_str = datetime.now().strftime("%A, %B %d at %H:%M")

    def _html_wrap(content_html, title, subtitle=""):
        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="color-scheme" content="light only">
  <meta name="supported-color-schemes" content="light only">
  <style>
    :root {{ color-scheme: light only; }}
    @media (prefers-color-scheme: dark) {{
      .email-header {{ background: linear-gradient(135deg,#1e293b 0%,#0f172a 100%) !important; }}
      .header-brand {{ color: #ffffff !important; }}
      .header-date  {{ color: #cbd5e1 !important; }}
      .header-title {{ color: #ffffff !important; }}
      .header-sub   {{ color: #cbd5e1 !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;">
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
            max-width:620px;margin:24px auto;background:#fff;border-radius:12px;
            overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1);">

  <!-- Header — dark background, white text. color-scheme: light only prevents inversion. -->
  <div class="email-header"
       style="background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
              padding:24px 28px 20px;mso-padding-alt:24px 28px 20px;">
    <div class="header-brand"
         style="font-size:22px;font-weight:700;color:#ffffff !important;margin-bottom:4px;">
      ⚡ B2Have Career Intelligence
    </div>
    <div class="header-date"
         style="font-size:14px;color:#cbd5e1 !important;">{date_str}</div>
    <div class="header-title"
         style="margin-top:12px;font-size:16px;font-weight:700;
                color:#ffffff !important;line-height:1.4;">{title}</div>
    {f'<div class="header-sub" style="font-size:13px;color:#cbd5e1 !important;margin-top:4px;">{subtitle}</div>' if subtitle else ''}
  </div>

  <!-- Content -->
  <div style="padding:24px 28px;">
    {content_html}
  </div>

  <!-- Footer -->
  <div style="background:#f8fafc;border-top:1px solid #e2e8f0;
              padding:14px 28px;font-size:12px;color:#94a3b8;">
    B2Have Career Coaching &bull; GTA/Toronto &bull; Career Intelligence System
  </div>
</div>
</body></html>"""

    # ── COACHING OPP ──────────────────────────────────────────────────────────
    if alert_type == ALERT_COACHING_OPP:
        items = alert.get("items", [])
        count = alert.get("count", 0)
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        drive_link = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else ""

        # Plain text
        plain_lines = [
            f"THIS WEEK IN CAREER CONVERSATIONS — {count} COACHING SIGNALS",
            "=" * 55,
            "Real discussions happening in career communities right now.",
            "",
        ]
        for i in items:
            segment = i.get("segment", "").replace("_", " ").title()
            title = i.get("title", "")
            quote = i.get("quote", "")
            reason = i.get("reason", "")
            url = i.get("url", "")
            theme = i.get("theme", "").replace("_", " ").title()
            plain_lines += [
                f"[{segment}] — {theme}",
                f"  {title}",
                f'  People are saying: "{quote}"' if quote else "",
                f"  Why it matters: {reason}" if reason else "",
                f"  Source: {url}",
                "",
            ]
        if drive_link:
            plain_lines.append(f"Full intelligence report: {drive_link}")
        plain_lines.append("\nACTION: These are real pain points this week. Use as hooks for LinkedIn, outreach, or coaching content.")
        plain = "\n".join(plain_lines)

        # HTML
        cards_html = ""
        for i in items:
            segment = i.get("segment", "")
            title = i.get("title", "")
            quote = i.get("quote", "")
            reason = i.get("reason", "")
            url = i.get("url", "")
            theme = i.get("theme", "")
            badge = _segment_badge(segment)
            theme_label = _theme_badge(theme)
            quote_html = (f'<div style="margin:10px 0;padding:10px 14px;background:#f0f9ff;'
                          f'border-left:3px solid #0ea5e9;border-radius:0 6px 6px 0;'
                          f'font-style:italic;color:#0c4a6e;font-size:14px;">'
                          f'&ldquo;{quote}&rdquo;</div>') if quote else ""
            reason_html = (f'<div style="font-size:13px;color:#475569;margin:6px 0;">'
                           f'<strong>Why it matters:</strong> {reason}</div>') if reason else ""
            url_html = (f'<div style="margin-top:8px;">'
                        f'<a href="{url}" style="font-size:12px;color:#6366f1;'
                        f'text-decoration:none;">Read source →</a></div>') if url else ""

            cards_html += f"""
<div style="border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:14px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
    {badge}
    <span style="font-size:12px;color:#64748b;">{theme_label}</span>
  </div>
  <div style="font-size:15px;font-weight:600;color:#1e293b;line-height:1.4;margin-bottom:6px;">{title}</div>
  {quote_html}
  {reason_html}
  {url_html}
</div>"""

        drive_html = ""
        if drive_link:
            drive_html = f"""<div style="margin-top:20px;padding:14px;background:#f8fafc;
border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
  <a href="{drive_link}" style="color:#6366f1;font-weight:600;font-size:14px;text-decoration:none;">
    📁 View Full Intelligence Report in Google Drive →
  </a>
</div>"""

        content = f"""
<div style="font-size:14px;color:#64748b;margin-bottom:18px;">
  Real discussions from career communities — {count} signals flagged this week.
  Use these as hooks for LinkedIn content, outreach, and coaching sessions.
</div>
{cards_html}
{drive_html}
<div style="margin-top:20px;padding:14px;background:#fef9c3;border-radius:8px;
            border-left:4px solid #f59e0b;">
  <strong style="color:#92400e;">This week's action:</strong>
  <span style="color:#78350f;font-size:14px;"> These are real pain points surfacing online right now.
  Create content or outreach around the themes above before they fade.</span>
</div>"""

        html = _html_wrap(content, f"Career Coaching Signals — {count} opportunities detected", date_str)
        return plain, html

    # ── VIRAL POST ────────────────────────────────────────────────────────────
    elif alert_type == ALERT_VIRAL_POST:
        plain = (f"VIRAL CAREER POST\n\n"
                 f"Title: {alert.get('title', '')}\n"
                 f"Score: {alert.get('score', 0):,} upvotes\n"
                 f"Theme: {alert.get('theme', '').replace('_', ' ').title()}\n"
                 f"Source: r/{alert.get('subreddit', '')}\n"
                 f"URL: {alert.get('url', '')}\n\n"
                 f"ACTION: Create a response post or video hook NOW — the audience is engaged.")
        html = _html_wrap(
            f"<p style='font-size:32px;text-align:center'>{alert.get('score',0):,} upvotes</p>"
            f"<p style='font-size:16px;font-weight:600;color:#1e293b'>{alert.get('title','')}</p>"
            f"<p>Source: r/{alert.get('subreddit','')} &bull; "
            f"<a href=\"{alert.get('url','')}\">View post</a></p>"
            f"<p style='color:#64748b'>This post is trending. Create content around this topic today.</p>",
            "Viral Career Post Detected"
        )
        return plain, html

    # ── MAJOR LAYOFF ──────────────────────────────────────────────────────────
    elif alert_type == ALERT_MAJOR_LAYOFF:
        affected = alert.get("affected", 0)
        plain = (f"MAJOR LAYOFF SIGNAL\n\n"
                 f"Title: {alert.get('title', '')}\n"
                 f"Estimated affected: {affected:,} workers\n"
                 f"Source: {alert.get('source', '')}\n"
                 f"URL: {alert.get('url', '')}\n\n"
                 f"ACTION: Layoff = coaching demand spike in 2-4 weeks. Draft an offer NOW.")
        html = _html_wrap(
            f"<p style='font-size:28px;text-align:center;color:#dc2626'>{affected:,} workers affected</p>"
            f"<p style='font-size:15px;font-weight:600;color:#1e293b'>{alert.get('title','')}</p>"
            f"<p><a href=\"{alert.get('url','')}\">View source →</a></p>"
            f"<div style='padding:12px;background:#fef2f2;border-radius:8px;border-left:4px solid #dc2626;'>"
            f"<strong>Coaching opportunity:</strong> Laid-off professionals will be searching for career coaching in 2-4 weeks. "
            f"Draft a targeted outreach message now.</div>",
            "Major Layoff Signal Detected"
        )
        return plain, html

    # ── KEYWORD SPIKE ─────────────────────────────────────────────────────────
    elif alert_type == ALERT_KEYWORD_SPIKE:
        theme = alert.get("theme", "").replace("_", " ").title()
        plain = (f"KEYWORD SPIKE: {theme}\n\n"
                 f"This week: {alert.get('current_count', 0)} signals\n"
                 f"Normal: {alert.get('baseline', 0)} signals\n"
                 f"Spike: {alert.get('multiplier', 0)}x above baseline\n\n"
                 f"ACTION: Prioritize content on '{theme}' this week.")
        html = _html_wrap(
            f"<p style='font-size:40px;text-align:center;color:#f59e0b'>{alert.get('multiplier',0)}x</p>"
            f"<p style='text-align:center;font-size:16px;font-weight:600;color:#1e293b'>"
            f"above normal for <em>{theme}</em></p>"
            f"<p style='text-align:center;color:#64748b'>{alert.get('current_count',0)} signals this week "
            f"vs {alert.get('baseline',0)} normally</p>"
            f"<div style='padding:12px;background:#fffbeb;border-radius:8px;border-left:4px solid #f59e0b;'>"
            f"Create content around <strong>{theme}</strong> this week — this topic is surging.</div>",
            f"Keyword Spike: {theme}"
        )
        return plain, html

    # ── SOURCE FAILURE ────────────────────────────────────────────────────────
    elif alert_type == ALERT_SOURCE_FAILURE:
        plain = (f"DATA SOURCE FAILURE\n\n"
                 f"Source: {alert.get('source', '')}\n"
                 f"Consecutive failures: {alert.get('consecutive_failures', 0)}\n"
                 f"Error: {alert.get('error', '')}\n\n"
                 f"ACTION: Check source config — may need login refresh or URL update.")
        html = _html_wrap(
            f"<p style='color:#dc2626;font-weight:600'>{alert.get('source','')} has failed "
            f"{alert.get('consecutive_failures',0)} times in a row.</p>"
            f"<p style='font-family:monospace;background:#f8fafc;padding:8px;border-radius:4px;font-size:12px'>"
            f"{alert.get('error','')}</p>"
            f"<p>Check your config — the source URL may have changed or require authentication.</p>",
            "Data Source Failure"
        )
        return plain, html

    # Fallback
    plain = f"Alert: {alert}"
    return plain, None


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
        plain_body, html_body = format_alert_body(alert)
        is_high_priority = alert.get("type") in [ALERT_MAJOR_LAYOFF, ALERT_SOURCE_FAILURE]

        if send_email_alert(subject, plain_body, html_body,
                            priority="high" if is_high_priority else "normal"):
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
