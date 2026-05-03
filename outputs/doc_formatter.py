"""
Document Formatter — B2Have Career Intelligence System
Formats enriched items into a structured Google Docs-compatible string
that NotebookLM can parse and query effectively.

Structure designed so NLM can answer questions like:
  "What career themes are most discussed this week?"
  "What are people saying about ATS rejection in Canada?"
  "Give me power quotes about job search burnout"
"""

from datetime import datetime
from collections import Counter


def format_weekly_doc(enriched_items, week_label, week_start, week_end):
    """
    Format a full weekly intelligence document.
    Returns a multi-section string ready for Google Docs.
    """
    sections = []

    # ── Document Header ───────────────────────────────────────────────────────
    sections.append(f"""CAREER INTELLIGENCE BRIEF — WEEK OF {week_label}
B2Have Career Coaching | GTA/Toronto Market Intelligence
Data Period: {week_start} to {week_end}
Total Signals Analyzed: {len(enriched_items)}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
════════════════════════════════════════════════════════════════
""")

    # ── Theme Distribution ─────────────────────────────────────────────────────
    theme_counts = Counter(item.get("theme", "unknown") for item in enriched_items)
    top_themes = theme_counts.most_common(8)

    sections.append("SECTION 1: TOP CAREER THEMES THIS WEEK\n" + "─" * 50)
    for rank, (theme, count) in enumerate(top_themes, 1):
        theme_display = theme.replace("_", " ").title()
        bar = "█" * min(count, 20)
        sections.append(f"{rank:2}. {theme_display:<30} {bar} ({count} signals)")
    sections.append("")

    # ── Top Signals (Score 8+) ────────────────────────────────────────────────
    top_signals = sorted(
        [i for i in enriched_items if i.get("relevance_score", 0) >= 8],
        key=lambda x: x.get("relevance_score", 0),
        reverse=True
    )[:20]

    sections.append("\nSECTION 2: HIGH-SIGNAL POSTS (Relevance 8-10)\n" + "─" * 50)
    for item in top_signals:
        sections.append(format_single_item(item))
        sections.append("")

    # ── Power Quotes ─────────────────────────────────────────────────────────
    quotes = [
        (item.get("power_quote"), item.get("theme"), item.get("source"),
         item.get("subreddit") or item.get("feed_name"), item.get("relevance_score", 0))
        for item in enriched_items
        if item.get("power_quote") and item.get("relevance_score", 0) >= 7
    ]
    quotes.sort(key=lambda x: x[4], reverse=True)

    sections.append("\nSECTION 3: POWER QUOTES — REAL VOICES\n" + "─" * 50)
    sections.append("(Exact language from job seekers — use for content, not verbatim)\n")
    for quote, theme, source, source_name, score in quotes[:15]:
        theme_display = (theme or "career").replace("_", " ").title()
        sections.append(f'"{quote}"')
        sections.append(f"  → Theme: {theme_display} | Source: {source_name} | Score: {score}/10\n")

    # ── Coaching Opportunities ────────────────────────────────────────────────
    coaching_items = [
        i for i in enriched_items
        if i.get("coaching_flag") and i.get("relevance_score", 0) >= 7
    ]

    sections.append("\nSECTION 4: COACHING OPPORTUNITY FLAGS\n" + "─" * 50)
    sections.append(f"({len(coaching_items)} posts where person clearly needs professional help)\n")
    for item in coaching_items[:15]:
        title = item.get("title", "")[:100]
        reason = item.get("enrichment", {}).get("coaching_reason", "")
        segment = item.get("audience_segment", "").replace("_", " ").title()
        source = item.get("subreddit") or item.get("feed_name", "")
        url = item.get("url", "")
        urgency = item.get("enrichment", {}).get("urgency", "")

        sections.append(f"• [{segment}] {title}")
        if reason:
            sections.append(f"  Coaching need: {reason}")
        if urgency == "high":
            sections.append(f"  ⚠ HIGH URGENCY")
        sections.append(f"  Source: {source} | {url}")
        sections.append("")

    # ── By Audience Segment ──────────────────────────────────────────────────
    segments = Counter(item.get("audience_segment", "unknown") for item in enriched_items)

    sections.append("\nSECTION 5: SIGNALS BY AUDIENCE SEGMENT\n" + "─" * 50)
    for segment, count in segments.most_common():
        seg_display = segment.replace("_", " ").title()
        seg_items = [i for i in enriched_items if i.get("audience_segment") == segment]
        top_seg_items = sorted(seg_items, key=lambda x: x.get("relevance_score", 0), reverse=True)[:3]

        sections.append(f"\n▸ {seg_display} ({count} signals)")
        for item in top_seg_items:
            title = item.get("title", "")[:80]
            score = item.get("relevance_score", 0)
            sections.append(f"  • [Score {score}] {title}")

    # ── Canada/GTA Specific ──────────────────────────────────────────────────
    canada_items = [
        i for i in enriched_items
        if i.get("enrichment", {}).get("canada_relevant") or
           i.get("subreddit") in ["canada", "toronto"]
    ]

    sections.append("\n\nSECTION 6: CANADA/GTA MARKET SIGNALS\n" + "─" * 50)
    for item in sorted(canada_items, key=lambda x: x.get("relevance_score", 0), reverse=True)[:10]:
        sections.append(format_single_item(item, brief=True))
        sections.append("")

    # ── All Items Reference ──────────────────────────────────────────────────
    sections.append("\nSECTION 7: COMPLETE SIGNAL INDEX\n" + "─" * 50)
    sections.append("(All items scored 6+ this week for NLM deep search)\n")
    for item in sorted(enriched_items, key=lambda x: x.get("relevance_score", 0), reverse=True):
        title = item.get("title", "")[:100]
        theme = (item.get("theme") or "").replace("_", " ").title()
        score = item.get("relevance_score", 0)
        source = item.get("subreddit") or item.get("feed_name", "")
        segment = (item.get("audience_segment") or "").replace("_", " ").title()
        sections.append(f"[{score}/10] [{theme}] [{segment}] {title} ({source})")

    return "\n".join(sections)


def format_single_item(item, brief=False):
    """Format a single enriched item for the document."""
    title = item.get("title", "Untitled")
    source = item.get("source", "")
    subreddit = item.get("subreddit", "")
    feed_name = item.get("feed_name", "")
    source_display = f"r/{subreddit}" if subreddit else feed_name
    score = item.get("relevance_score", 0)
    theme = (item.get("theme") or "").replace("_", " ").title()
    segment = (item.get("audience_segment") or "").replace("_", " ").title()
    url = item.get("url", "")
    power_quote = item.get("power_quote", "")
    coaching_flag = item.get("coaching_flag", False)

    enrichment = item.get("enrichment", {})
    summary = enrichment.get("summary", "")
    sentiment = enrichment.get("sentiment", "")
    urgency = enrichment.get("urgency", "")
    content_angle = enrichment.get("content_angle", "")

    lines = [
        f"▸ {title}",
        f"  Source: {source_display} | Theme: {theme} | Score: {score}/10 | Segment: {segment}"
    ]

    if not brief:
        if summary:
            lines.append(f"  Summary: {summary}")
        if power_quote:
            lines.append(f'  Quote: "{power_quote}"')
        if coaching_flag:
            coaching_reason = enrichment.get("coaching_reason", "")
            lines.append(f"  🎯 COACHING OPPORTUNITY: {coaching_reason}")
        if content_angle:
            lines.append(f"  Content angle: {content_angle}")
        if sentiment or urgency:
            lines.append(f"  Sentiment: {sentiment} | Urgency: {urgency}")

        # Include post body excerpt for Reddit
        body = item.get("body", "")
        if body and len(body) > 50:
            lines.append(f"  Post excerpt: {body[:400]}...")

        # Include top comment
        top_comments = item.get("top_comments", [])
        if top_comments:
            top = top_comments[0]
            lines.append(f"  Top comment ({top.get('score', 0)} upvotes): {top.get('body', '')[:300]}")

        lines.append(f"  URL: {url}")

    return "\n".join(lines)
