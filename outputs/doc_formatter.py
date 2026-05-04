"""
Document Formatter — B2Have Career Intelligence System
Formats enriched items into a comprehensive daily research brief
structured for NotebookLM deep querying and coach reference use.

Daily docs are created each day. On Sunday a weekly_rollup.py synthesizes
all 7 daily docs into a "Weekly Narrative" using Claude Sonnet.

NotebookLM can answer questions like:
  "What are the top career pain points today?"
  "What exact language do clients use about AI anxiety?"
  "Give me 5 LinkedIn hooks about burnout I can use today"
  "What coaching questions should I ask a laid-off tech executive?"
  "What do Canadians think about remote work this week?"
"""

from datetime import datetime
from collections import Counter


DIVIDER_HEAVY = "═" * 70
DIVIDER_LIGHT = "─" * 60
DIVIDER_DOT = "·" * 60


def format_daily_doc(enriched_items, day_label, day_display):
    """
    Format a single day's intelligence brief.
    Wrapper that calls format_weekly_doc with daily labels.
    """
    return format_weekly_doc(enriched_items, day_label, day_label, day_label,
                             doc_type="daily", day_display=day_display)


def format_weekly_doc(enriched_items, week_label, week_start, week_end,
                      doc_type="daily", day_display=None):
    """
    Format a full weekly intelligence document.
    Returns a multi-section string ready for Google Docs / NotebookLM.
    """
    sections = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    display = day_display or week_label

    # Sort items by relevance score throughout
    items_by_score = sorted(enriched_items, key=lambda x: x.get("relevance_score", 0), reverse=True)
    coaching_items = [i for i in items_by_score if i.get("coaching_flag")]
    high_signal = [i for i in items_by_score if i.get("relevance_score", 0) >= 8]
    canada_items = [i for i in items_by_score if
                    i.get("enrichment", {}).get("canada_relevant") or
                    i.get("subreddit") in ["canada", "toronto", "ontario", "torontoJobs"]]

    # ── COVER PAGE ───────────────────────────────────────────────────────────
    sections.append(f"""{DIVIDER_HEAVY}
CAREER INTELLIGENCE BRIEF — {display}
B2Have Career Coaching | GTA / Toronto Market Intelligence
{DIVIDER_HEAVY}

Date: {week_label}
Generated: {now_str}
Total Signals Analyzed: {len(enriched_items)}
High-Signal Items (8-10): {len(high_signal)}
Coaching Opportunity Flags: {len(coaching_items)}
Canada-Specific Signals: {len(canada_items)}

PURPOSE: This daily brief is designed for NotebookLM deep-search and coach reference.
Each day produces one file. On Sunday, weekly_rollup.py synthesizes all 7 into a
Weekly Narrative. Ask NotebookLM: "What are clients saying about AI this week?",
"Give me LinkedIn hooks about burnout", or "What coaching questions should I
ask a mid-career professional who hates their job?"
""")

    # ── SECTION 1: EXECUTIVE SUMMARY ─────────────────────────────────────────
    theme_counts = Counter(item.get("theme", "unknown") for item in enriched_items)
    top_themes = theme_counts.most_common(6)

    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 1: EXECUTIVE SUMMARY — WHAT'S HAPPENING THIS WEEK
{DIVIDER_HEAVY}

TOP CAREER THEMES (by signal volume):
""")
    for rank, (theme, count) in enumerate(top_themes, 1):
        theme_display = theme.replace("_", " ").title()
        bar = "█" * min(count * 2, 30)
        sections.append(f"  {rank}. {theme_display:<35} {bar} ({count} signals)")

    # Dominant narrative
    if top_themes:
        top_theme = top_themes[0][0].replace("_", " ").title()
        top_count = top_themes[0][1]
        sections.append(f"""
DOMINANT NARRATIVE THIS WEEK:
The most discussed topic is {top_theme} with {top_count} signals.
This represents a strong coaching opportunity — professionals across career
stages are actively grappling with this theme and seeking guidance.

KEY SIGNALS AT A GLANCE:""")
        for item in items_by_score[:5]:
            title = item.get("title", "")[:90]
            score = item.get("relevance_score", 0)
            segment = (item.get("audience_segment") or "").replace("_", " ").title()
            sections.append(f"  [{score}/10] [{segment}] {title}")

    # ── SECTION 2: FULL SIGNAL ANALYSIS ──────────────────────────────────────
    sections.append(f"""

{DIVIDER_HEAVY}
SECTION 2: FULL SIGNAL ANALYSIS — EVERY ITEM IN DEPTH
{DIVIDER_HEAVY}
(Use this section to find detailed analysis, quotes, coaching questions,
and content ideas for each article/post collected this week)
""")

    for idx, item in enumerate(items_by_score, 1):
        sections.append(format_single_item_full(item, idx))
        sections.append("")

    # ── SECTION 3: STATISTICS & DATA BANK ────────────────────────────────────
    all_stats = []
    for item in items_by_score:
        stats = item.get("key_statistics", [])
        source_name = item.get("feed_name") or item.get("subreddit") or "Unknown"
        title_short = item.get("title", "")[:60]
        for stat in stats:
            if stat and len(stat) > 5:
                all_stats.append((stat, source_name, title_short))

    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 3: STATISTICS & DATA BANK
{DIVIDER_HEAVY}
(Key numbers and statistics extracted from all sources this week.
Ask NotebookLM: "What are the key statistics about burnout this week?")

Total statistics extracted: {len(all_stats)}
""")
    if all_stats:
        for stat, source, title in all_stats:
            sections.append(f"  • {stat}")
            sections.append(f"    ↳ Source: {source} | {title}")
            sections.append("")
    else:
        sections.append("  No statistics extracted this week. Run with more data sources for richer analysis.")

    # ── SECTION 4: REAL VOICES — WHAT PEOPLE ARE SAYING ──────────────────────
    all_power_quotes = [
        (item.get("power_quote"), item.get("theme"), item.get("feed_name") or item.get("subreddit"),
         item.get("relevance_score", 0), item.get("audience_segment"))
        for item in items_by_score
        if item.get("power_quote") and item.get("relevance_score", 0) >= 6
    ]

    all_client_phrases = []
    for item in items_by_score:
        phrases = item.get("what_clients_say", [])
        for phrase in phrases:
            if phrase:
                all_client_phrases.append((phrase, item.get("theme"), item.get("title", "")[:60]))

    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 4: REAL VOICES — WHAT PEOPLE ARE SAYING
{DIVIDER_HEAVY}
(Exact language from real people — use for content writing, intake forms,
social media posts. Ask NLM: "What language do frustrated job seekers use?")

4A. POWER QUOTES (from articles — emotionally resonant moments)
{DIVIDER_LIGHT}
""")
    for quote, theme, source, score, segment in all_power_quotes:
        theme_display = (theme or "career").replace("_", " ").title()
        seg_display = (segment or "").replace("_", " ").title()
        sections.append(f'"{quote}"')
        sections.append(f"  → Theme: {theme_display} | Segment: {seg_display} | Source: {source} | Relevance: {score}/10")
        sections.append("")

    sections.append(f"""
4B. CLIENT INTAKE LANGUAGE (phrases clients use — directly from AI analysis)
{DIVIDER_LIGHT}
(These are the exact phrases your clients are likely to say when they walk in.
Use for intake forms, consultation prompts, and empathy in outreach.)
""")
    if all_client_phrases:
        # Group by theme
        by_theme = {}
        for phrase, theme, title in all_client_phrases:
            key = (theme or "general").replace("_", " ").title()
            by_theme.setdefault(key, []).append((phrase, title))

        for theme_name, phrases in sorted(by_theme.items()):
            sections.append(f"  [{theme_name}]")
            for phrase, title in phrases:
                sections.append(f'  • "{phrase}"')
            sections.append("")
    else:
        sections.append("  (Will populate when more data is collected)")

    # ── SECTION 5: COACHING PLAYBOOK ─────────────────────────────────────────
    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 5: COACHING PLAYBOOK — QUESTIONS & OPPORTUNITIES
{DIVIDER_HEAVY}
(Use this section to prepare for client sessions.
Ask NLM: "What coaching questions should I ask someone afraid of AI?")

Total coaching opportunity flags this week: {len(coaching_items)}
""")

    for item in coaching_items:
        title = item.get("title", "")
        segment = (item.get("audience_segment") or "").replace("_", " ").title()
        theme = (item.get("theme") or "").replace("_", " ").title()
        coaching_reason = item.get("enrichment", {}).get("coaching_reason", "")
        urgency = item.get("enrichment", {}).get("urgency", "")
        coaching_qs = item.get("coaching_questions", [])
        url = item.get("url", "")

        urgency_tag = " ⚠ HIGH URGENCY" if urgency == "high" else ""
        sections.append(f"{'─' * 50}")
        sections.append(f"[{segment}] — {theme}{urgency_tag}")
        sections.append(f"Signal: {title}")
        if coaching_reason:
            sections.append(f"Why coaching helps: {coaching_reason}")
        if coaching_qs:
            sections.append("Coaching questions to ask:")
            for q in coaching_qs:
                sections.append(f"  Q: {q}")
        sections.append(f"Source: {url}")
        sections.append("")

    # ── SECTION 6: CONTENT CALENDAR ──────────────────────────────────────────
    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 6: CONTENT CALENDAR — LINKEDIN HOOKS & IDEAS
{DIVIDER_HEAVY}
(Ready-to-use content ideas based on this week's signals.
Ask NLM: "Give me 5 LinkedIn post ideas for this week")

6A. LINKEDIN HOOKS (opening lines — sorted by relevance)
{DIVIDER_LIGHT}
""")
    all_hooks = []
    for item in items_by_score:
        hooks = item.get("linkedin_hooks", [])
        score = item.get("relevance_score", 0)
        theme = (item.get("theme") or "").replace("_", " ").title()
        for hook in hooks:
            if hook:
                all_hooks.append((hook, theme, score))

    all_hooks.sort(key=lambda x: x[2], reverse=True)
    for hook, theme, score in all_hooks:
        sections.append(f"  [{theme}] {hook}")
        sections.append("")

    sections.append(f"""
6B. CONTENT ANGLES (blog posts, videos, workshops)
{DIVIDER_LIGHT}
""")
    all_angles = []
    for item in items_by_score:
        angles = item.get("content_angles", [])
        theme = (item.get("theme") or "").replace("_", " ").title()
        score = item.get("relevance_score", 0)
        for angle in angles:
            if angle:
                all_angles.append((angle, theme, score))

    all_angles.sort(key=lambda x: x[2], reverse=True)
    for angle, theme, score in all_angles[:20]:
        sections.append(f"  [{theme}] {angle}")
        sections.append("")

    # ── SECTION 7: CANADA / GTA SIGNALS ─────────────────────────────────────
    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 7: CANADA / GTA MARKET SIGNALS
{DIVIDER_HEAVY}
(Signals specifically relevant to the Ontario/GTA market.
Ask NLM: "What's happening in the GTA job market this week?")

Canada-specific signals found: {len(canada_items)}
""")
    if canada_items:
        for item in canada_items:
            title = item.get("title", "")
            source = item.get("feed_name") or item.get("subreddit", "")
            score = item.get("relevance_score", 0)
            canada_ctx = item.get("canada_context", "")
            summary = item.get("enrichment", {}).get("summary", "")
            url = item.get("url", "")
            sections.append(f"▸ [{score}/10] {title}")
            sections.append(f"  Source: {source}")
            if canada_ctx:
                sections.append(f"  GTA Context: {canada_ctx}")
            if summary:
                sections.append(f"  Summary: {summary}")
            sections.append(f"  URL: {url}")
            sections.append("")
    else:
        sections.append("  No Canada-specific signals this week. Consider adding Canadian HR Reporter,\n"
                        "  Globe and Mail Careers, and Toronto subreddits to your sources.")

    # ── SECTION 8: SEGMENT BREAKDOWN ─────────────────────────────────────────
    segments = Counter(item.get("audience_segment", "unknown") for item in enriched_items)

    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 8: SIGNALS BY AUDIENCE SEGMENT
{DIVIDER_HEAVY}
(Which client segments are most active this week?
Ask NLM: "What are senior executives worried about this week?")
""")
    for segment, count in segments.most_common():
        seg_display = segment.replace("_", " ").title()
        seg_items = sorted(
            [i for i in enriched_items if i.get("audience_segment") == segment],
            key=lambda x: x.get("relevance_score", 0), reverse=True
        )
        sections.append(f"▸ {seg_display} — {count} signals this week")
        for item in seg_items[:4]:
            title = item.get("title", "")[:85]
            score = item.get("relevance_score", 0)
            theme = (item.get("theme") or "").replace("_", " ").title()
            sections.append(f"  [{score}/10] [{theme}] {title}")
        sections.append("")

    # ── SECTION 9: COMPLETE SOURCE INDEX ─────────────────────────────────────
    sections.append(f"""
{DIVIDER_HEAVY}
SECTION 9: COMPLETE SOURCE INDEX
{DIVIDER_HEAVY}
(Every signal this week with full metadata — for deep NLM search)
""")
    for item in items_by_score:
        title = item.get("title", "")
        theme = (item.get("theme") or "").replace("_", " ").title()
        score = item.get("relevance_score", 0)
        source = item.get("feed_name") or (f"r/{item.get('subreddit')}" if item.get("subreddit") else "Unknown")
        segment = (item.get("audience_segment") or "").replace("_", " ").title()
        url = item.get("url", "")
        coaching = " [COACHING FLAG]" if item.get("coaching_flag") else ""
        canada = " [CANADA]" if item.get("enrichment", {}).get("canada_relevant") else ""
        sections.append(f"[{score}/10] [{theme}] [{segment}]{coaching}{canada}")
        sections.append(f"  {title}")
        sections.append(f"  {source} | {url}")
        sections.append("")

    sections.append(f"""
{DIVIDER_HEAVY}
END OF BRIEF — Week of {week_label}
B2Have Career Intelligence | Generated {now_str}
{DIVIDER_HEAVY}""")

    return "\n".join(sections)


def format_single_item_full(item, idx):
    """
    Format a single enriched item with tiered detail based on relevance score:
      Score 8–10: Full detail — all fields + article body excerpt (500 chars)
      Score 6–7:  Standard — summary, power quote, coaching questions, hooks (no body)
      Score 5:    Brief — title, source, score, 2-sentence summary only
    This keeps the document at a readable ~30–50 pages instead of 300.
    """
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
    coaching_reason = enrichment.get("coaching_reason", "")
    canada_ctx = item.get("canada_context") or enrichment.get("canada_context", "")
    key_stats = item.get("key_statistics", [])
    client_phrases = item.get("what_clients_say", [])
    coaching_qs = item.get("coaching_questions", [])
    linkedin_hooks = item.get("linkedin_hooks", [])
    content_angles = item.get("content_angles", [])

    urgency_marker = " ⚠ HIGH URGENCY" if urgency == "high" else ""
    coaching_marker = " 🎯 COACHING FLAG" if coaching_flag else ""

    # ── SCORE 5: Brief index entry only ──────────────────────────────────────
    if score <= 5:
        lines = [
            f"{'─' * 40}",
            f"SIGNAL #{idx:02d} | Score: {score}/10 | Theme: {theme}",
            f"  {title}",
            f"  {source_display} | {url}",
        ]
        if summary:
            # Just first sentence for score-5 items
            first_sentence = summary.split(". ")[0] + "."
            lines.append(f"  {first_sentence}")
        return "\n".join(lines)

    # ── SCORE 6-7: Standard detail (no raw article body) ─────────────────────
    lines = [
        f"{'─' * 60}",
        f"SIGNAL #{idx:02d} | Score: {score}/10 | Theme: {theme} | Segment: {segment}",
        f"{'─' * 60}",
        f"TITLE: {title}",
        f"Source: {source_display}{urgency_marker}{coaching_marker}",
        f"Sentiment: {sentiment.title() if sentiment else 'N/A'} | Urgency: {urgency.title() if urgency else 'N/A'}",
        f"URL: {url}",
    ]

    if summary:
        lines.append(f"\nSUMMARY:")
        lines.append(summary)

    if power_quote:
        lines.append(f'\nPOWER QUOTE:')
        lines.append(f'"{power_quote}"')

    if coaching_flag and coaching_reason:
        lines.append(f"\nCOACHING OPPORTUNITY:")
        lines.append(f"  {coaching_reason}")

    if coaching_qs:
        lines.append(f"\nCOACHING QUESTIONS:")
        for q in coaching_qs:
            lines.append(f"  • {q}")

    if linkedin_hooks:
        lines.append(f"\nLINKEDIN HOOKS:")
        for hook in linkedin_hooks:
            lines.append(f"  → {hook}")

    # Reddit comments for mid-range items
    top_comments = item.get("top_comments", [])
    if top_comments:
        lines.append(f"\nTOP COMMUNITY RESPONSES:")
        for i, c in enumerate(top_comments[:3]):
            upvotes = c.get("score", 0)
            body_text = c.get("body", "")[:200]
            lines.append(f"  Comment {i+1} ({upvotes} upvotes): {body_text}")

    # ── SCORE 8+: Full detail with all fields + article body excerpt ──────────
    if score >= 8:
        if key_stats:
            lines.append(f"\nKEY STATISTICS:")
            for stat in key_stats:
                lines.append(f"  • {stat}")

        if canada_ctx:
            lines.append(f"\nGTA/CANADA RELEVANCE:")
            lines.append(f"  {canada_ctx}")

        if client_phrases:
            lines.append(f"\nWHAT CLIENTS SAY (intake language):")
            for phrase in client_phrases:
                lines.append(f'  • "{phrase}"')

        if content_angles:
            lines.append(f"\nCONTENT ANGLES:")
            for angle in content_angles:
                lines.append(f"  → {angle}")

        # Article body — capped at 500 chars for score 8+ only
        body = item.get("body", "")
        if body and len(body) > 100:
            lines.append(f"\nFULL POST TEXT (excerpt):")
            lines.append(body[:500])

        full_text = item.get("full_text", "")
        if full_text and len(full_text) > 100:
            lines.append(f"\nARTICLE BODY (excerpt):")
            lines.append(full_text[:500])

        # More comments for high-score items
        if top_comments:
            lines.append(f"\nTOP COMMUNITY RESPONSES:")
            for i, c in enumerate(top_comments[:5]):
                upvotes = c.get("score", 0)
                body_text = c.get("body", "")[:300]
                lines.append(f"  Comment {i+1} ({upvotes} upvotes): {body_text}")

    return "\n".join(lines)
