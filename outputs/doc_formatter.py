"""
Document Formatter — B2Have Career Intelligence System
Formats enriched items into a structured daily research brief.

format_daily_doc()  → returns list[{"text": str, "style": str}]
                       Styles: HEADING_1 / HEADING_2 / HEADING_3 / NORMAL_TEXT
                       Consumed by drive_writer.append_structured_content_to_doc()

format_weekly_doc() → returns plain string (used by weekly_rollup.py for NotebookLM)

NotebookLM can answer questions like:
  "What are the top career pain points today?"
  "What exact language do clients use about AI anxiety?"
  "Give me 5 LinkedIn hooks about burnout I can use today"
  "What coaching questions should I ask a laid-off tech executive?"
  "What do Canadians think about remote work this week?"
"""

from datetime import datetime
from collections import Counter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b(text, style="NORMAL_TEXT"):
    """Shorthand block constructor."""
    return {"text": str(text), "style": style}


def _fmt_theme(theme):
    return (theme or "general").replace("_", " ").title()


def _fmt_seg(segment):
    return (segment or "").replace("_", " ").title()


# ── Daily Formatter (structured blocks) ───────────────────────────────────────

def format_daily_doc(enriched_items, day_label, day_display):
    """
    Format a single day's intelligence brief as structured heading blocks.
    Returns: list[{"text": str, "style": str}]

    Styles map directly to Google Docs named paragraph styles:
      HEADING_1 → H1 (large, bold)
      HEADING_2 → H2 (article titles)
      HEADING_3 → H3 (source/score metadata)
      NORMAL_TEXT → body paragraph
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    blocks = []

    # Sort items by relevance score
    items_by_score = sorted(enriched_items, key=lambda x: x.get("relevance_score", 0), reverse=True)
    coaching_items = [i for i in items_by_score if i.get("coaching_flag")]
    high_signal = [i for i in items_by_score if i.get("relevance_score", 0) >= 8]
    mid_signal = [i for i in items_by_score if 6 <= i.get("relevance_score", 0) <= 7]
    lower_signal = [i for i in items_by_score if i.get("relevance_score", 0) == 5]
    canada_items = [i for i in items_by_score if
                    i.get("enrichment", {}).get("canada_relevant") or
                    i.get("subreddit") in ["canada", "toronto", "ontario", "torontoJobs"]]

    # ── TITLE PAGE ─────────────────────────────────────────────────────────────
    blocks.append(_b(f"Career Intelligence Brief — {day_display}", "HEADING_1"))
    blocks.append(_b("B2Have Career Coaching | GTA / Toronto Market Intelligence", "NORMAL_TEXT"))
    blocks.append(_b(f"Generated: {now_str}", "NORMAL_TEXT"))

    # ── OVERVIEW ───────────────────────────────────────────────────────────────
    blocks.append(_b("Overview", "HEADING_1"))
    blocks.append(_b(
        f"Total Signals Analysed: {len(enriched_items)}     |     "
        f"High-Signal (8–10): {len(high_signal)}     |     "
        f"Coaching Flags: {len(coaching_items)}     |     "
        f"Canada-Specific: {len(canada_items)}",
        "NORMAL_TEXT"
    ))

    # ── TOP THEMES ─────────────────────────────────────────────────────────────
    theme_counts = Counter(item.get("theme", "unknown") for item in enriched_items)
    top_themes = theme_counts.most_common(6)

    blocks.append(_b("Top Career Themes This Run", "HEADING_1"))
    for rank, (theme, count) in enumerate(top_themes, 1):
        bar = "█" * min(count * 2, 30)
        blocks.append(_b(f"{rank}. {_fmt_theme(theme)} — {count} signals  {bar}", "NORMAL_TEXT"))

    if top_themes:
        top_theme = _fmt_theme(top_themes[0][0])
        top_count = top_themes[0][1]
        blocks.append(_b(
            f"Dominant narrative: {top_theme} with {top_count} signals. "
            f"Strong coaching opportunity — professionals across career stages are actively grappling with this theme.",
            "NORMAL_TEXT"
        ))

    # ── KEY SIGNALS AT A GLANCE ────────────────────────────────────────────────
    blocks.append(_b("Key Signals at a Glance (Top 5)", "HEADING_2"))
    for item in items_by_score[:5]:
        title = item.get("title", "")[:100]
        score = item.get("relevance_score", 0)
        segment = _fmt_seg(item.get("audience_segment"))
        blocks.append(_b(f"[{score}/10]  [{segment}]  {title}", "NORMAL_TEXT"))

    # ── HIGH-SIGNAL STORIES (8+) ───────────────────────────────────────────────
    if high_signal:
        blocks.append(_b(f"High-Signal Stories — Score 8 to 10  ({len(high_signal)} items)", "HEADING_1"))
        blocks.append(_b(
            "Full analysis: summary, power quote, coaching questions, LinkedIn hooks, statistics, and client phrases.",
            "NORMAL_TEXT"
        ))
        for idx, item in enumerate(high_signal, 1):
            blocks.extend(_item_blocks_full(item, idx))

    # ── MID-SIGNAL STORIES (6-7) ───────────────────────────────────────────────
    if mid_signal:
        blocks.append(_b(f"Standard Stories — Score 6 to 7  ({len(mid_signal)} items)", "HEADING_1"))
        blocks.append(_b("Summary, power quote, coaching questions, and LinkedIn hooks.", "NORMAL_TEXT"))
        for idx, item in enumerate(mid_signal, 1):
            blocks.extend(_item_blocks_standard(item, idx))

    # ── LOWER SIGNAL STORIES (5) ───────────────────────────────────────────────
    if lower_signal:
        blocks.append(_b(f"Brief Signals — Score 5  ({len(lower_signal)} items)", "HEADING_1"))
        for idx, item in enumerate(lower_signal, 1):
            blocks.extend(_item_blocks_brief(item, idx))

    # ── COACHING PLAYBOOK ──────────────────────────────────────────────────────
    if coaching_items:
        blocks.append(_b(f"Coaching Playbook — {len(coaching_items)} Flagged Opportunities", "HEADING_1"))
        blocks.append(_b(
            "Items flagged by AI as having direct coaching application for your client base.",
            "NORMAL_TEXT"
        ))
        for item in coaching_items:
            blocks.extend(_coaching_blocks(item))

    # ── CANADA / GTA SIGNALS ───────────────────────────────────────────────────
    blocks.append(_b(f"Canada / GTA Market Signals — {len(canada_items)} items", "HEADING_1"))
    if canada_items:
        for item in canada_items:
            title = item.get("title", "")
            source = item.get("feed_name") or item.get("subreddit", "")
            score = item.get("relevance_score", 0)
            canada_ctx = item.get("canada_context") or item.get("enrichment", {}).get("canada_context", "")
            summary = item.get("enrichment", {}).get("summary", "")
            url = item.get("url", "")
            blocks.append(_b(f"[{score}/10]  {title}", "HEADING_3"))
            blocks.append(_b(f"Source: {source}  |  {url}", "NORMAL_TEXT"))
            if canada_ctx:
                blocks.append(_b(f"GTA Context: {canada_ctx}", "NORMAL_TEXT"))
            if summary:
                blocks.append(_b(f"Summary: {summary}", "NORMAL_TEXT"))
    else:
        blocks.append(_b(
            "No Canada-specific signals this run. "
            "Canadian HR Reporter, CBC Business, Benefits Canada, and Talent Canada feeds are active.",
            "NORMAL_TEXT"
        ))

    # ── CONTENT CALENDAR ───────────────────────────────────────────────────────
    all_hooks = []
    all_angles = []
    for item in items_by_score:
        theme = _fmt_theme(item.get("theme"))
        score = item.get("relevance_score", 0)
        for hook in item.get("linkedin_hooks", []):
            if hook:
                all_hooks.append((hook, theme, score))
        for angle in item.get("content_angles", []):
            if angle:
                all_angles.append((angle, theme, score))

    all_hooks.sort(key=lambda x: x[2], reverse=True)
    all_angles.sort(key=lambda x: x[2], reverse=True)

    blocks.append(_b("Content Calendar — LinkedIn Hooks & Content Angles", "HEADING_1"))
    if all_hooks:
        blocks.append(_b("LinkedIn Hooks (sorted by relevance)", "HEADING_2"))
        for hook, theme, score in all_hooks[:20]:
            blocks.append(_b(f"[{theme}]  {hook}", "NORMAL_TEXT"))

    if all_angles:
        blocks.append(_b("Content Angles — Blog Posts, Videos, Workshops", "HEADING_2"))
        for angle, theme, score in all_angles[:15]:
            blocks.append(_b(f"[{theme}]  {angle}", "NORMAL_TEXT"))

    # ── STATISTICS BANK ────────────────────────────────────────────────────────
    all_stats = []
    for item in items_by_score:
        source_name = item.get("feed_name") or item.get("subreddit") or "Unknown"
        for stat in item.get("key_statistics", []):
            if stat and len(stat) > 5:
                all_stats.append((stat, source_name))

    if all_stats:
        blocks.append(_b(f"Statistics & Data Bank — {len(all_stats)} facts extracted", "HEADING_1"))
        blocks.append(_b(
            "Key numbers from all sources. Ask NotebookLM: "
            "\"What are the key statistics about burnout this week?\"",
            "NORMAL_TEXT"
        ))
        for stat, source in all_stats:
            blocks.append(_b(f"• {stat}  ↳ {source}", "NORMAL_TEXT"))

    # ── POWER QUOTES ───────────────────────────────────────────────────────────
    all_power_quotes = [
        (item.get("power_quote"), item.get("theme"), item.get("feed_name") or item.get("subreddit"),
         item.get("relevance_score", 0), item.get("audience_segment"))
        for item in items_by_score
        if item.get("power_quote") and item.get("relevance_score", 0) >= 6
    ]
    if all_power_quotes:
        blocks.append(_b("Real Voices — Power Quotes", "HEADING_1"))
        blocks.append(_b(
            "Emotionally resonant quotes for content, coaching empathy, and intake language.",
            "NORMAL_TEXT"
        ))
        for quote, theme, source, score, segment in all_power_quotes:
            seg_display = _fmt_seg(segment)
            theme_display = _fmt_theme(theme)
            blocks.append(_b(f'"{quote}"', "NORMAL_TEXT"))
            blocks.append(_b(
                f"Theme: {theme_display}  |  Segment: {seg_display}  |  Source: {source}  |  Relevance: {score}/10",
                "NORMAL_TEXT"
            ))

    # ── AUDIENCE SEGMENT BREAKDOWN ─────────────────────────────────────────────
    segments = Counter(item.get("audience_segment", "unknown") for item in enriched_items)
    blocks.append(_b("Signals by Audience Segment", "HEADING_1"))
    for segment, count in segments.most_common():
        seg_display = _fmt_seg(segment)
        seg_items = sorted(
            [i for i in enriched_items if i.get("audience_segment") == segment],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        blocks.append(_b(f"{seg_display} — {count} signals", "HEADING_2"))
        for item in seg_items[:4]:
            title = item.get("title", "")[:90]
            score = item.get("relevance_score", 0)
            theme = _fmt_theme(item.get("theme"))
            blocks.append(_b(f"[{score}/10]  [{theme}]  {title}", "NORMAL_TEXT"))

    # ── SOURCE INDEX ───────────────────────────────────────────────────────────
    blocks.append(_b("Complete Source Index", "HEADING_1"))
    blocks.append(_b(
        "Every signal with full metadata for deep NotebookLM search.",
        "NORMAL_TEXT"
    ))
    for item in items_by_score:
        title = item.get("title", "")
        theme = _fmt_theme(item.get("theme"))
        score = item.get("relevance_score", 0)
        source = item.get("feed_name") or (f"r/{item.get('subreddit')}" if item.get("subreddit") else "Unknown")
        segment = _fmt_seg(item.get("audience_segment"))
        url = item.get("url", "")
        coaching = " [COACHING FLAG]" if item.get("coaching_flag") else ""
        canada = " [CANADA]" if item.get("enrichment", {}).get("canada_relevant") else ""
        blocks.append(_b(f"[{score}/10]  [{theme}]  [{segment}]{coaching}{canada}  |  {source}", "NORMAL_TEXT"))
        blocks.append(_b(f"{title}  |  {url}", "NORMAL_TEXT"))

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    blocks.append(_b(f"End of Brief — {day_display}  |  B2Have Career Intelligence  |  {now_str}", "HEADING_3"))

    return blocks


# ── Item Block Formatters ─────────────────────────────────────────────────────

def _item_blocks_full(item, idx):
    """Return full-detail blocks for a score 8+ item."""
    blocks = []
    title = item.get("title", "Untitled")
    subreddit = item.get("subreddit", "")
    feed_name = item.get("feed_name", "")
    source_display = f"r/{subreddit}" if subreddit else feed_name
    score = item.get("relevance_score", 0)
    theme = _fmt_theme(item.get("theme"))
    segment = _fmt_seg(item.get("audience_segment"))
    url = item.get("url", "")
    coaching_flag = item.get("coaching_flag", False)

    enrichment = item.get("enrichment", {})
    summary = enrichment.get("summary", "")
    sentiment = enrichment.get("sentiment", "")
    urgency = enrichment.get("urgency", "")
    coaching_reason = enrichment.get("coaching_reason", "")
    canada_ctx = item.get("canada_context") or enrichment.get("canada_context", "")
    power_quote = item.get("power_quote", "")
    key_stats = item.get("key_statistics", [])
    client_phrases = item.get("what_clients_say", [])
    coaching_qs = item.get("coaching_questions", [])
    linkedin_hooks = item.get("linkedin_hooks", [])
    content_angles = item.get("content_angles", [])

    urgency_tag = "  ⚠ HIGH URGENCY" if urgency == "high" else ""
    coaching_tag = "  🎯 COACHING FLAG" if coaching_flag else ""

    blocks.append(_b(title, "HEADING_2"))
    blocks.append(_b(
        f"Source: {source_display}  |  Score: {score}/10  |  Theme: {theme}  |  Segment: {segment}"
        f"{urgency_tag}{coaching_tag}",
        "HEADING_3"
    ))
    blocks.append(_b(
        f"Sentiment: {sentiment.title() if sentiment else 'N/A'}  |  "
        f"Urgency: {urgency.title() if urgency else 'N/A'}  |  {url}",
        "NORMAL_TEXT"
    ))

    if summary:
        blocks.append(_b(f"Summary: {summary}", "NORMAL_TEXT"))

    if power_quote:
        blocks.append(_b(f'Power Quote: "{power_quote}"', "NORMAL_TEXT"))

    if key_stats:
        blocks.append(_b("Key Statistics:", "NORMAL_TEXT"))
        for stat in key_stats:
            blocks.append(_b(f"  • {stat}", "NORMAL_TEXT"))

    if coaching_flag and coaching_reason:
        blocks.append(_b(f"Coaching Opportunity: {coaching_reason}", "NORMAL_TEXT"))

    if coaching_qs:
        blocks.append(_b("Coaching Questions:", "NORMAL_TEXT"))
        for q in coaching_qs:
            blocks.append(_b(f"  Q: {q}", "NORMAL_TEXT"))

    if linkedin_hooks:
        blocks.append(_b("LinkedIn Hooks:", "NORMAL_TEXT"))
        for hook in linkedin_hooks:
            blocks.append(_b(f"  → {hook}", "NORMAL_TEXT"))

    if canada_ctx:
        blocks.append(_b(f"GTA / Canada Relevance: {canada_ctx}", "NORMAL_TEXT"))

    if client_phrases:
        blocks.append(_b("What Clients Say (intake language):", "NORMAL_TEXT"))
        for phrase in client_phrases:
            blocks.append(_b(f'  • "{phrase}"', "NORMAL_TEXT"))

    if content_angles:
        blocks.append(_b("Content Angles:", "NORMAL_TEXT"))
        for angle in content_angles:
            blocks.append(_b(f"  → {angle}", "NORMAL_TEXT"))

    # Article body excerpt (score 8+ only)
    body = item.get("body", "")
    if body and len(body) > 100:
        blocks.append(_b(f"Post Text (excerpt): {body[:400]}", "NORMAL_TEXT"))

    full_text = item.get("full_text", "")
    if full_text and len(full_text) > 100:
        blocks.append(_b(f"Article Body (excerpt): {full_text[:400]}", "NORMAL_TEXT"))

    # Top comments
    top_comments = item.get("top_comments", [])
    if top_comments:
        blocks.append(_b("Top Community Responses:", "NORMAL_TEXT"))
        for i, c in enumerate(top_comments[:5]):
            upvotes = c.get("score", 0)
            body_text = c.get("body", "")[:280]
            blocks.append(_b(f"  Comment {i+1} ({upvotes} upvotes): {body_text}", "NORMAL_TEXT"))

    return blocks



def _item_blocks_standard(item, idx):
    """Return standard-detail blocks for a score 6-7 item."""
    blocks = []
    title = item.get("title", "Untitled")
    subreddit = item.get("subreddit", "")
    feed_name = item.get("feed_name", "")
    source_display = f"r/{subreddit}" if subreddit else feed_name
    score = item.get("relevance_score", 0)
    theme = _fmt_theme(item.get("theme"))
    segment = _fmt_seg(item.get("audience_segment"))
    url = item.get("url", "")
    coaching_flag = item.get("coaching_flag", False)
    coaching_tag = "  🎯" if coaching_flag else ""

    enrichment = item.get("enrichment", {})
    summary = enrichment.get("summary", "")
    sentiment = enrichment.get("sentiment", "")
    urgency = enrichment.get("urgency", "")
    coaching_reason = enrichment.get("coaching_reason", "")
    power_quote = item.get("power_quote", "")
    coaching_qs = item.get("coaching_questions", [])
    linkedin_hooks = item.get("linkedin_hooks", [])

    blocks.append(_b(title, "HEADING_2"))
    blocks.append(_b(
        f"Source: {source_display}  |  Score: {score}/10  |  Theme: {theme}  |  "
        f"Sentiment: {sentiment or 'N/A'}  |  Urgency: {urgency or 'N/A'}{coaching_tag}",
        "HEADING_3"
    ))
    blocks.append(_b(url, "NORMAL_TEXT"))

    if summary:
        blocks.append(_b(f"Summary: {summary}", "NORMAL_TEXT"))
    if power_quote:
        blocks.append(_b(f'Power Quote: "{power_quote}"', "NORMAL_TEXT"))
    if coaching_flag and coaching_reason:
        blocks.append(_b(f"Coaching Opportunity: {coaching_reason}", "NORMAL_TEXT"))
    if coaching_qs:
        qs_text = "  |  ".join(f"Q: {q}" for q in coaching_qs[:3])
        blocks.append(_b(qs_text, "NORMAL_TEXT"))
    if linkedin_hooks:
        blocks.append(_b("Hooks: " + "  //  ".join(linkedin_hooks[:3]), "NORMAL_TEXT"))

    top_comments = item.get("top_comments", [])
    for c in top_comments[:3]:
        body_text = c.get("body", "")[:200]
        upvotes = c.get("score", 0)
        blocks.append(_b(f"  Community ({upvotes} upvotes): {body_text}", "NORMAL_TEXT"))

    return blocks


def _item_blocks_brief(item, idx):
    """Return brief entry for a score 5 item (index entry only)."""
    blocks = []
    title = item.get("title", "Untitled")
    subreddit = item.get("subreddit", "")
    feed_name = item.get("feed_name", "")
    source_display = f"r/{subreddit}" if subreddit else feed_name
    score = item.get("relevance_score", 0)
    theme = _fmt_theme(item.get("theme"))
    url = item.get("url", "")
    summary = item.get("enrichment", {}).get("summary", "")

    blocks.append(_b(f"[{score}/10]  [{theme}]  {title}", "HEADING_3"))
    blocks.append(_b(f"Source: {source_display}  |  {url}", "NORMAL_TEXT"))
    if summary:
        first_sentence = summary.split(". ")[0] + "."
        blocks.append(_b(first_sentence, "NORMAL_TEXT"))
    return blocks


def _coaching_blocks(item):
    """Return coaching playbook blocks for a coaching-flagged item."""
    blocks = []
    title = item.get("title", "")
    segment = _fmt_seg(item.get("audience_segment"))
    theme = _fmt_theme(item.get("theme"))
    coaching_reason = item.get("enrichment", {}).get("coaching_reason", "")
    urgency = item.get("enrichment", {}).get("urgency", "")
    coaching_qs = item.get("coaching_questions", [])
    url = item.get("url", "")

    urgency_tag = "  ⚠ HIGH URGENCY" if urgency == "high" else ""
    blocks.append(_b(f"{segment} -- {theme}{urgency_tag}", "HEADING_2"))
    blocks.append(_b(f"Signal: {title}", "NORMAL_TEXT"))
    if coaching_reason:
        blocks.append(_b(f"Why coaching helps: {coaching_reason}", "NORMAL_TEXT"))
    if coaching_qs:
        blocks.append(_b("Coaching Questions to Ask:", "HEADING_3"))
        for q in coaching_qs:
            blocks.append(_b(f"  Q: {q}", "NORMAL_TEXT"))
    blocks.append(_b(f"Source: {url}", "NORMAL_TEXT"))
    return blocks


# ── Weekly Formatter (plain string for NotebookLM / weekly_rollup.py) ─────────

DIVIDER_HEAVY = "=" * 70
DIVIDER_LIGHT = "-" * 60


def format_weekly_doc(enriched_items, week_label, week_start, week_end,
                      doc_type="daily", day_display=None):
    """
    Format a full weekly intelligence document as a plain string.
    Used by weekly_rollup.py -- NotebookLM ingests this directly.
    Returns a multi-section string.
    """
    sections = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    display = day_display or week_label

    items_by_score = sorted(enriched_items, key=lambda x: x.get("relevance_score", 0), reverse=True)
    coaching_items = [i for i in items_by_score if i.get("coaching_flag")]
    high_signal = [i for i in items_by_score if i.get("relevance_score", 0) >= 8]
    canada_items = [i for i in items_by_score if
                    i.get("enrichment", {}).get("canada_relevant") or
                    i.get("subreddit") in ["canada", "toronto", "ontario", "torontoJobs"]]

    sections.append(
        f"{DIVIDER_HEAVY}\n"
        f"CAREER INTELLIGENCE BRIEF -- {display}\n"
        f"B2Have Career Coaching | GTA / Toronto Market Intelligence\n"
        f"{DIVIDER_HEAVY}\n\n"
        f"Date: {week_label}\n"
        f"Generated: {now_str}\n"
        f"Total Signals Analyzed: {len(enriched_items)}\n"
        f"High-Signal Items (8-10): {len(high_signal)}\n"
        f"Coaching Opportunity Flags: {len(coaching_items)}\n"
        f"Canada-Specific Signals: {len(canada_items)}\n"
    )

    theme_counts = Counter(item.get("theme", "unknown") for item in enriched_items)
    top_themes = theme_counts.most_common(6)
    sections.append(f"\n{DIVIDER_HEAVY}\nSECTION 1: EXECUTIVE SUMMARY\n{DIVIDER_HEAVY}\n\nTOP THEMES:\n")
    for rank, (theme, count) in enumerate(top_themes, 1):
        bar = "X" * min(count * 2, 30)
        sections.append(f"  {rank}. {_fmt_theme(theme):<35} {bar} ({count} signals)")

    sections.append(f"\n\n{DIVIDER_HEAVY}\nSECTION 2: FULL SIGNAL ANALYSIS\n{DIVIDER_HEAVY}\n")
    for idx, item in enumerate(items_by_score, 1):
        sections.append(format_single_item_full(item, idx))
        sections.append("")

    all_stats = []
    for item in items_by_score:
        source_name = item.get("feed_name") or item.get("subreddit") or "Unknown"
        title_short = item.get("title", "")[:60]
        for stat in item.get("key_statistics", []):
            if stat and len(stat) > 5:
                all_stats.append((stat, source_name, title_short))

    sections.append(f"\n{DIVIDER_HEAVY}\nSECTION 3: STATISTICS & DATA BANK\n{DIVIDER_HEAVY}\n")
    for stat, source, title in all_stats:
        sections.append(f"  - {stat}")
        sections.append(f"    Source: {source} | {title}")
        sections.append("")

    all_power_quotes = [
        (item.get("power_quote"), item.get("theme"),
         item.get("feed_name") or item.get("subreddit"),
         item.get("relevance_score", 0), item.get("audience_segment"))
        for item in items_by_score
        if item.get("power_quote") and item.get("relevance_score", 0) >= 6
    ]
    sections.append(f"\n{DIVIDER_HEAVY}\nSECTION 4: REAL VOICES\n{DIVIDER_HEAVY}\n")
    for quote, theme, source, score, segment in all_power_quotes:
        sections.append(f'"{quote}"')
        sections.append(f"  -> {_fmt_theme(theme)} | {_fmt_seg(segment)} | {source} | {score}/10")
        sections.append("")

    sections.append(f"\n{DIVIDER_HEAVY}\nSECTION 5: COACHING PLAYBOOK\n{DIVIDER_HEAVY}\n")
    for item in coaching_items:
        title = item.get("title", "")
        segment = _fmt_seg(item.get("audience_segment"))
        theme = _fmt_theme(item.get("theme"))
        coaching_reason = item.get("enrichment", {}).get("coaching_reason", "")
        coaching_qs = item.get("coaching_questions", [])
        url = item.get("url", "")
        sections.append("-" * 50)
        sections.append(f"[{segment}] -- {theme}")
        sections.append(f"Signal: {title}")
        if coaching_reason:
            sections.append(f"Why coaching helps: {coaching_reason}")
        for q in coaching_qs:
            sections.append(f"  Q: {q}")
        sections.append(f"Source: {url}")
        sections.append("")

    sections.append(f"\n{DIVIDER_HEAVY}\nSECTION 6: CANADA / GTA SIGNALS\n{DIVIDER_HEAVY}\n")
    for item in canada_items:
        title = item.get("title", "")
        source = item.get("feed_name") or item.get("subreddit", "")
        score = item.get("relevance_score", 0)
        canada_ctx = item.get("canada_context", "")
        summary = item.get("enrichment", {}).get("summary", "")
        url = item.get("url", "")
        sections.append(f"[{score}/10] {title}")
        sections.append(f"  Source: {source}")
        if canada_ctx:
            sections.append(f"  GTA Context: {canada_ctx}")
        if summary:
            sections.append(f"  Summary: {summary}")
        sections.append(f"  URL: {url}")
        sections.append("")

    sections.append(f"\n{DIVIDER_HEAVY}\nEND OF BRIEF -- {week_label} | Generated {now_str}\n{DIVIDER_HEAVY}")
    return "\n".join(sections)


def format_single_item_full(item, idx):
    """
    Format a single enriched item as plain text (used by format_weekly_doc).
    Tiered detail: score 8+: full, 6-7: standard, 5: brief.
    """
    title = item.get("title", "Untitled")
    subreddit = item.get("subreddit", "")
    feed_name = item.get("feed_name", "")
    source_display = f"r/{subreddit}" if subreddit else feed_name
    score = item.get("relevance_score", 0)
    theme = _fmt_theme(item.get("theme"))
    segment = _fmt_seg(item.get("audience_segment"))
    url = item.get("url", "")
    power_quote = item.get("power_quote", "")
    coaching_flag = item.get("coaching_flag", False)

    enrichment = item.get("enrichment", {})
    summary = enrichment.get("summary", "")
    sentiment = enrichment.get("sentiment", "")
    urgency = enrichment.get("urgency", "")
    coaching_reason = enrichment.get("coaching_reason", "")
    canada_ctx = item.get("canada_context") or enrichment.get("canada_context", "")
    key_stats = item.get("key_statistics", [])
    client_phrases = item.get("what_clients_say", [])
    coaching_qs = item.get("coaching_questions", [])
    linkedin_hooks = item.get("linkedin_hooks", [])
    content_angles = item.get("content_angles", [])

    urgency_marker = " HIGH URGENCY" if urgency == "high" else ""
    coaching_marker = " COACHING FLAG" if coaching_flag else ""

    if score <= 5:
        lines = [
            "-" * 40,
            f"SIGNAL #{idx:02d} | Score: {score}/10 | Theme: {theme}",
            f"  {title}",
            f"  {source_display} | {url}",
        ]
        if summary:
            lines.append(f"  {summary.split('. ')[0]}.")
        return "\n".join(lines)

    lines = [
        "-" * 60,
        f"SIGNAL #{idx:02d} | Score: {score}/10 | Theme: {theme} | Segment: {segment}",
        "-" * 60,
        f"TITLE: {title}",
        f"Source: {source_display}{urgency_marker}{coaching_marker}",
        f"Sentiment: {sentiment.title() if sentiment else 'N/A'} | Urgency: {urgency.title() if urgency else 'N/A'}",
        f"URL: {url}",
    ]

    if summary:
        lines.append(f"\nSUMMARY:\n{summary}")
    if power_quote:
        lines.append(f'\nPOWER QUOTE:\n"{power_quote}"')
    if coaching_flag and coaching_reason:
        lines.append(f"\nCOACHING OPPORTUNITY:\n  {coaching_reason}")
    if coaching_qs:
        lines.append("\nCOACHING QUESTIONS:")
        for q in coaching_qs:
            lines.append(f"  - {q}")
    if linkedin_hooks:
        lines.append("\nLINKEDIN HOOKS:")
        for hook in linkedin_hooks:
            lines.append(f"  -> {hook}")

    top_comments = item.get("top_comments", [])
    if top_comments:
        lines.append("\nTOP COMMUNITY RESPONSES:")
        for i, c in enumerate(top_comments[:3]):
            lines.append(f"  Comment {i+1} ({c.get('score', 0)} upvotes): {c.get('body', '')[:200]}")

    if score >= 8:
        if key_stats:
            lines.append("\nKEY STATISTICS:")
            for stat in key_stats:
                lines.append(f"  - {stat}")
        if canada_ctx:
            lines.append(f"\nGTA/CANADA RELEVANCE:\n  {canada_ctx}")
        if client_phrases:
            lines.append("\nWHAT CLIENTS SAY:")
            for phrase in client_phrases:
                lines.append(f'  - "{phrase}"')
        if content_angles:
            lines.append("\nCONTENT ANGLES:")
            for angle in content_angles:
                lines.append(f"  -> {angle}")
        body = item.get("body", "")
        if body and len(body) > 100:
            lines.append(f"\nFULL POST TEXT (excerpt):\n{body[:500]}")
        full_text = item.get("full_text", "")
        if full_text and len(full_text) > 100:
            lines.append(f"\nARTICLE BODY (excerpt):\n{full_text[:500]}")
        if top_comments:
            lines.append("\nTOP COMMUNITY RESPONSES (extended):")
            for i, c in enumerate(top_comments[:5]):
                lines.append(f"  Comment {i+1} ({c.get('score', 0)} upvotes): {c.get('body', '')[:300]}")

    return "\n".join(lines)
