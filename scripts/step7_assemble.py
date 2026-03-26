#!/usr/bin/env python3
"""
Step 7: HTML Assembly
NO MODEL. Pure Python template injection.
Reads all JSON from Steps 1-6 and injects into playbook-template.html.
Uses exact CSS class patterns from playbook-template.html.
"""

import json, sys, html as html_mod, re, math
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path("/home/openclaw/playbook-skill")
TEMPLATE_PATH = SKILL_ROOT / "templates" / "playbook-template.html"

CHEVRON_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>'
CHEVRON_SVG_16 = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>'
CHEVRON_SVG_12 = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>'
SHIELD_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'

# ClimateDoor Growth Pod team - real team data
CD_TEAM = {
    "nick": {"name": "Nick Findler", "role": "Co-founder & Principal", "focus": "Capital strategy, investor relationships, deal architecture"},
    "chad": {"name": "Chad Rickaby", "role": "Executive Director / Strategy", "focus": "Business strategy, executive advisory, organizational design"},
    "sam": {"name": "Sam Kullar", "role": "Project Execution Lead", "focus": "Operations, client delivery, project management"},
    "sophie": {"name": "Sophie Kennedy", "role": "Grant Strategy", "focus": "Grant writing, government funding programs, compliance"},
    "ash": {"name": "Ash Kumar", "role": "BD Lead", "focus": "Business development, outreach, pipeline building"},
    "jamie": {"name": "Jamie Moran", "role": "BD", "focus": "Business development, market research, lead qualification"},
    "tiff": {"name": "Tiff", "role": "Indigenous Partnerships", "focus": "Indigenous community engagement, ICP4 relationships, cultural competency"},
    "rizz": {"name": "Rizz Jiwani", "role": "Creative Director", "focus": "Brand, content, marketing, visual design"},
}


def esc(s):
    """HTML-escape a string, handle None. Replace em dashes with commas."""
    if s is None:
        return ""
    out = html_mod.escape(str(s))
    # Never use em dashes
    out = out.replace("\u2014", ",").replace("\u2013", ",").replace("&mdash;", ",").replace("&ndash;", ",")
    return out


def initials(name):
    """Get initials from a name."""
    if not name:
        return "?"
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][0].upper()


def safe_str(v):
    """Convert value to string safely, handling dicts/lists."""
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


def load_data(slug: str) -> dict:
    d = SKILL_ROOT / "data" / slug
    data = {}
    for key, fn in [("s1", "step1-company.json"), ("s2", "step2-investors.json"),
                     ("s2b", "step2b-contacts.json"),
                     ("s3", "step3-grants.json"), ("s4", "step4-market.json"),
                     ("s5", "step5-experts.json"), ("s6", "step6-synthesis.json")]:
        p = d / fn
        if p.exists():
            with open(p) as f:
                data[key] = json.load(f)
        else:
            print(f"  WARN: missing {p}")
            data[key] = {}
    return data


# ── Counts ──────────────────────────────────────────────

def counts(data):
    s2 = data.get("s2", {})
    s3 = data.get("s3", {})
    s4 = data.get("s4", {})
    s5 = data.get("s5", {})
    s6 = data.get("s6", {})
    c = {
        "investors": len(s2.get("investors", [])),
        "grants": len(s3.get("direct_grants", [])),
        "segments": len(s4.get("buyer_segments", [])),
        "signals": len(s4.get("market_signals", [])),
        "opportunities": len(s6.get("creative_opportunities", [])),
        "experts": len(s5.get("expert_matches", [])),
        "indigenous": len(s4.get("indigenous_opportunities", [])),
        "events": len(s4.get("conference_targets", [])),
    }
    c["total"] = sum(c.values())
    return c


# ── HTML builders ───────────────────────────────────────

def build_alerts(data):
    """Build alert cards using .al .al-h / .al-s pattern."""
    alerts = data.get("s6", {}).get("alerts", [])
    if not alerts:
        return ""
    items = []
    for i, a in enumerate(alerts):
        if isinstance(a, str):
            parts = a.split(":", 1)
            headline = parts[0].strip()
            detail = parts[1].strip() if len(parts) > 1 else ""
        else:
            headline = a.get("headline", "")
            detail = a.get("detail", a.get("sentence", ""))
        # First alert is high priority, rest are standard
        cls = "al-h" if i == 0 else "al-s"
        delay = f" d{i + 1}" if i < 6 else ""
        items.append(
            f'<div class="al {cls} sr{delay}" data-editable>'
            f'<div class="al-d"></div>'
            f'<div>'
            f'<div class="al-lb">{"PRIORITY ALERT" if cls == "al-h" else "ALERT"}</div>'
            f'<div class="al-tx" data-editable><strong>{esc(headline)}</strong> {esc(detail)}</div>'
            f'</div></div>'
        )
    return "\n".join(items)


def build_hero_tags(data):
    comp = data.get("s1", {}).get("company", {})
    tags = []
    if comp.get("sector"):
        tags.append(f'<span class="htg htg-s" data-editable>{esc(comp["sector"])}</span>')
    if comp.get("sub_sector"):
        tags.append(f'<span class="htg htg-s" data-editable>{esc(comp["sub_sector"])}</span>')
    if comp.get("stage"):
        tags.append(f'<span class="htg htg-c" data-editable>{esc(comp["stage"])}</span>')
    geo = comp.get("geography", {}).get("hq", "")
    if geo:
        tags.append(f'<span class="htg htg-g" data-editable>{esc(geo)}</span>')
    trl = comp.get("trl")
    if trl:
        tags.append(f'<span class="htg htg-g" data-editable>TRL {trl}</span>')
    return " ".join(tags)


# ── Playbook Tab: Strategy Pillars + Questions + Competitive Position ──

def _pillar_type_class(name):
    """Map pillar name to CSS pillar class."""
    n = name.lower().replace(" ", "_")
    if "capital" in n or "investor" in n:
        return "sc-cap"
    if "grant" in n:
        return "sc-gra"
    if "sales" in n or "partnership" in n:
        return "sc-sal"
    if "market" in n or "signal" in n:
        return "sc-mkt"
    return "sc-cap"


def _pillar_pill(name):
    """Map pillar name to pill label."""
    n = name.lower().replace("_", " ")
    if "capital" in n or "investor" in n:
        return "CAPITAL"
    if "grant" in n:
        return "GRANTS"
    if "sales" in n or "partnership" in n:
        return "SALES"
    if "market" in n or "signal" in n:
        return "SIGNALS"
    return name.upper()


def _parse_detail_bold(text):
    """Parse **bold** markdown from detail strings into <strong> tags."""
    if not text:
        return ""
    escaped = esc(text)
    # Convert **text** to <strong>text</strong>
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    return escaped


def build_playbook_tab(data):
    """Strategy pillars as .sc cards + Key Questions as .qi + Competitive Position as .comp-c."""
    s6 = data.get("s6", {})
    pillars = s6.get("strategy_pillars", {})
    questions = s6.get("key_questions", [])
    comp_pos = s6.get("competitive_position", {})

    parts = []

    # Section header
    parts.append('<div class="sl">STRATEGY</div>')
    parts.append('<div class="sh">Strategy Pillars</div>')
    parts.append('<div class="sd">Core strategies across capital, grants, sales, and market intelligence.</div>')

    # Build pillar list from dict or list
    if isinstance(pillars, dict):
        pillar_list = []
        for k, v in pillars.items():
            if isinstance(v, dict):
                pillar_list.append({"key": k, "name": k.replace("_", " ").title(), **v})
            else:
                pillar_list.append({"key": k, "name": k.replace("_", " ").title(), "summary": str(v), "details": []})
    elif isinstance(pillars, list):
        pillar_list = pillars
    else:
        pillar_list = []

    parts.append('<div class="sstack">')
    for i, p in enumerate(pillar_list):
        if isinstance(p, str):
            continue
        pname = p.get("name", p.get("pillar", "Strategy"))
        pkey = p.get("key", pname.lower().replace(" ", "_"))
        summary = p.get("summary", "")
        items = p.get("details", p.get("items", []))
        if not isinstance(items, list):
            items = []

        type_cls = _pillar_type_class(pkey)
        pill_label = _pillar_pill(pkey)
        delay = f" d{i + 1}" if i < 6 else ""
        n_details = len(items)

        parts.append(f'<div class="sc {type_cls} sr{delay}">')
        parts.append(f'  <div class="sc-top" onclick="togSC(this)">')
        parts.append(f'    <div class="sc-bar"></div>')
        parts.append(f'    <div class="sc-body">')
        parts.append(f'      <div class="sc-pill">{pill_label}</div>')
        parts.append(f'      <div class="sc-tt">{esc(pname)}</div>')
        parts.append(f'      <div class="sc-ds">{esc(summary)}</div>')
        parts.append(f'    </div>')
        parts.append(f'    <div class="sc-met"><div class="sc-v">{n_details}</div><div class="sc-u">DETAILS</div></div>')
        parts.append(f'    <div class="sc-tog">{CHEVRON_SVG}</div>')
        parts.append(f'  </div>')
        parts.append(f'  <div class="sc-det"><div class="sc-det-in">')
        parts.append(f'    <div class="dg">')
        for item in items[:8]:
            if isinstance(item, str):
                # Parse markdown bold from string items like "**Bold**: detail"
                parsed = _parse_detail_bold(item)
                # Try to split into label/value on first colon after bold
                match = re.match(r'^<strong>(.+?)</strong>:?\s*(.*)', parsed)
                if match:
                    label = match.group(1).upper()
                    value = match.group(2) if match.group(2) else parsed
                    parts.append(f'      <div class="di"><div class="di-l">{label}</div><div class="di-v">{value}</div></div>')
                else:
                    parts.append(f'      <div class="di"><div class="di-l">DETAIL</div><div class="di-v">{parsed}</div></div>')
            elif isinstance(item, dict):
                label = item.get("label", item.get("term", "DETAIL"))
                detail = item.get("detail", item.get("description", ""))
                parts.append(f'      <div class="di"><div class="di-l">{esc(label).upper()}</div><div class="di-v">{_parse_detail_bold(detail)}</div></div>')
        parts.append(f'    </div>')
        parts.append(f'  </div></div>')
        parts.append(f'</div>')

    parts.append('</div>')  # end .sstack

    # Key Questions - .qi pattern
    parts.append('<div class="sl" style="margin-top:48px">DISCOVERY</div>')
    parts.append('<div class="sh">Key Questions for Call 1</div>')
    parts.append('<div class="sd">Critical unknowns that must be resolved to activate the playbook.</div>')

    parts.append('<div class="q-s">')
    for i, q in enumerate(questions):
        if isinstance(q, dict):
            question = q.get("question", "")
            context = q.get("context", q.get("why_it_matters", ""))
            category = q.get("category", "")
        else:
            question = str(q)
            context = ""
            category = ""
        delay = f" d{(i % 6) + 1}" if i < 6 else ""
        parts.append(
            f'<div class="qi sr{delay}">'
            f'<div class="qn">{i + 1}</div>'
            f'<div>'
            f'<div class="qt">{esc(question)}</div>'
        )
        if context:
            parts.append(f'<div class="qc">{esc(context)}</div>')
        parts.append('</div></div>')
    parts.append('</div>')  # end .q-s

    # Competitive Position removed from Playbook tab - lives only in Landscape tab

    return "\n".join(parts)




# ── Overview Tab ──

CD_CAPABILITIES = [
    {"title": "Go-to-Market Strategy", "desc": "Multi-channel sales acceleration, buyer segment targeting, conference strategy, and pipeline building."},
    {"title": "Capital Orchestration", "desc": "Investor matching across 2,645+ contacts, deal structuring, pitch refinement, and warm introductions."},
    {"title": "Non-Dilutive Funding", "desc": "Grant scanning, application support, SR&ED claims, and stacking strategies across federal and provincial programs."},
    {"title": "Indigenous Partnerships", "desc": "Community-first engagement, procurement pathways, and benefit-sharing structures with First Nations communities."},
]

# ── 11 Standardized Intake Questions ──
INTAKE_QUESTIONS = [
    "What about this playbook felt accurate?",
    "What about this playbook felt inaccurate?",
    "Tell us about your company and team.",
    "What are your top 1-3 objectives right now?",
    "What are your biggest constraints today?",
    "How do you create demand today? Sales teams? Founder-led sales?",
    "What is working? What is not?",
    "Any signed pilots, POs, or LOIs?",
    "Who are your customer segments?",
    "Tell us about your fundraising.",
    "What's your non-dilutive/grants situation?",
    "Any market entry plans for new markets?",
    "Any notes on First Nations/Indigenous opportunities?",
    "Which of our services are of interest to you?",
]


def build_overview_tab(data):
    """Build overview tab with market-driven 'Opportunity We See' hero, acceleration cards, capabilities."""
    s1 = data.get("s1", {})
    s4 = data.get("s4", {})
    s6 = data.get("s6", {})
    comp = s1.get("company", {})

    # ── Build headline from market data (not company claims) ──
    market = s4.get("market_sizing", {})
    sector_temp = s4.get("sector_temperature", {})
    signals = s4.get("market_signals", [])

    # Extract TAM - short dollar figure only, max 60 chars
    tam_short = ""
    if isinstance(market, dict):
        tam_raw = market.get("tam", "")
        if isinstance(tam_raw, dict):
            tam_full = tam_raw.get("value", "")
        elif isinstance(tam_raw, str):
            tam_full = tam_raw
        else:
            tam_full = str(tam_raw) if tam_raw else ""
        # Truncate: strip parentheticals and explanatory text
        tam_short = tam_full
        if "(" in tam_short:
            tam_short = tam_short[:tam_short.index("(")].strip().rstrip(",")
        # If still too long, trim at comma after a reasonable length
        if len(tam_short) > 60:
            parts = tam_short.split(",")
            tam_short = parts[0]
            if len(parts) > 1 and len(parts[0] + ", " + parts[1].strip()) <= 60:
                tam_short = parts[0] + ", " + parts[1].strip()

    # Use synthesis-generated headline if available (step6 pre-generates these)
    headline = s6.get("opportunity_headline", "")
    subheadline = s6.get("opportunity_subheadline", "")
    tam_override = s6.get("tam_short", "")
    if tam_override:
        tam_short = tam_override

    # Fallback headline: extract from sector_temperature evidence
    if not headline:
        temp_evidence = []
        if isinstance(sector_temp, dict):
            temp_evidence = sector_temp.get("evidence", [])

        # Prefer evidence items with market sizing indicators
        market_keywords = ["cagr", "billion", "trillion", "market size", "market valued", "projected to"]
        anti_keywords = ["grant", "awarded", "received", "funding from", "coalition"]
        best_ev = ""
        fallback_ev = ""
        if temp_evidence and isinstance(temp_evidence, list):
            for ev in temp_evidence:
                if isinstance(ev, dict):
                    text = ev.get("data_point", ev.get("signal", ""))
                elif isinstance(ev, str):
                    text = ev
                else:
                    continue
                if not text:
                    continue
                text_lower = text.lower()
                # Skip grant-like items
                if any(ak in text_lower for ak in anti_keywords):
                    continue
                if not fallback_ev:
                    fallback_ev = text
                # Check for market sizing keywords
                if any(kw in text_lower for kw in market_keywords):
                    best_ev = text
                    break

        headline = best_ev or fallback_ev
        if not headline:
            if tam_short:
                headline = f"Market opportunity of {tam_short}"
            else:
                headline = comp.get("description", "Significant market opportunity identified.")

        # Strip source citations (anything after em dash, or "— Source, Date" patterns)
        for sep in [" \u2014 ", " -- ", " \u2013 "]:
            if sep in headline:
                headline = headline[:headline.index(sep)]
        # Strip parenthetical citations like (2023), (Source Name), etc.
        headline = re.sub(r'\s*\([^)]{0,40}\)', '', headline)
        # Trim to a clean sentence break if possible, then cap at 15 words
        # If headline has a comma after word 8+, cut there for punchiness
        words = headline.split()
        if len(words) > 15:
            # Try to find a natural break (comma, period) between words 8-15
            trimmed = " ".join(words[:15])
            for i in range(min(14, len(words)-1), 7, -1):
                partial = " ".join(words[:i])
                if partial.rstrip().endswith(",") or partial.rstrip().endswith("."):
                    headline = partial.rstrip(",").rstrip(".")
                    break
            else:
                headline = trimmed

    # Fallback subheadline: build from market signals
    if not subheadline:
        narrative_parts = []
        for sig in signals[:3]:
            if isinstance(sig, dict):
                sig_text = sig.get("signal", sig.get("headline", ""))
                if sig_text:
                    # Strip source citations from signals too
                    for sep in [" \u2014 ", " -- ", " \u2013 "]:
                        if sep in sig_text:
                            sig_text = sig_text[:sig_text.index(sep)]
                    narrative_parts.append(sig_text)
            elif isinstance(sig, str):
                narrative_parts.append(sig)

        if narrative_parts:
            # Join and cap at 200 chars
            subheadline = ". ".join(narrative_parts[:2])
            if len(subheadline) > 200:
                subheadline = subheadline[:197] + "..."
        else:
            subheadline = comp.get("description", "")[:200]

    # Acceleration cards from creative opportunities
    creative_opps = s6.get("creative_opportunities", [])
    accel_cards = []
    for opp in creative_opps[:4]:
        if isinstance(opp, dict):
            accel_cards.append({
                "title": opp.get("name", "Opportunity"),
                "desc": opp.get("narrative", "")[:200],
            })

    parts = []

    # ── THE OPPORTUNITY WE SEE hero (with TAM folded in) ──
    parts.append('<div class="wk-hero sr" data-editable>')
    parts.append('  <div class="wk-eyebrow">THE OPPORTUNITY WE SEE</div>')
    parts.append(f'  <div class="wk-headline" data-editable>{esc(headline)}</div>')
    parts.append(f'  <div class="wk-narrative" data-editable>{esc(subheadline)}</div>')
    if tam_short:
        parts.append(f'  <div class="wk-tam">')
        parts.append(f'    <div class="wk-tam-amount" data-editable>{esc(tam_short[:60])}</div>')
        parts.append(f'    <div class="wk-tam-label">TAM</div>')
        parts.append(f'  </div>')
    parts.append('</div>')

    # ── MORE WAYS WE CAN ACCELERATE YOU ──
    if accel_cards:
        parts.append('<div class="accel-section sr d2">')
        parts.append('  <div class="sl">ACCELERATION</div>')
        parts.append('  <div class="sh" data-editable>More Ways We Can Accelerate You</div>')
        parts.append('  <div class="accel-grid">')
        icons = [
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
        ]
        for i, card in enumerate(accel_cards):
            icon = icons[i % len(icons)]
            parts.append(f'    <div class="accel-card" data-editable>')
            parts.append(f'      <div class="accel-card-icon">{icon}</div>')
            parts.append(f'      <div class="accel-card-title" data-editable>{esc(card["title"])}</div>')
            parts.append(f'      <div class="accel-card-desc" data-editable>{esc(card["desc"])}</div>')
            parts.append(f'    </div>')
        parts.append('  </div>')
        parts.append('</div>')

    # ── HOW CLIMATEDOOR DOES THIS ──
    parts.append('<div class="cap-section sr d3">')
    parts.append('  <div class="sl">CAPABILITIES</div>')
    parts.append('  <div class="sh" data-editable>How ClimateDoor Does This</div>')
    parts.append('  <div class="cap-grid">')
    for cap in CD_CAPABILITIES:
        parts.append(f'    <div class="cap-card" data-editable>')
        parts.append(f'      <div class="cap-card-title" data-editable>{esc(cap["title"])}</div>')
        parts.append(f'      <div class="cap-card-desc" data-editable>{esc(cap["desc"])}</div>')
        parts.append(f'    </div>')
    parts.append('  </div>')
    parts.append('</div>')

    # ── Strategy Pillars ──
    pillars = s6.get("strategy_pillars", {})
    if pillars:
        parts.append('<div class="sl" style="margin-top:48px">STRATEGY</div>')
        parts.append('<div class="sh" data-editable>Strategy Pillars</div>')
        parts.append('<div class="sd" data-editable>Core strategies across capital, grants, sales, and market intelligence.</div>')

        pillar_list = []
        if isinstance(pillars, dict):
            for k, v in pillars.items():
                if isinstance(v, dict):
                    pillar_list.append({"key": k, "name": k.replace("_", " ").title(), **v})
                else:
                    pillar_list.append({"key": k, "name": k.replace("_", " ").title(), "summary": str(v), "details": []})
        elif isinstance(pillars, list):
            pillar_list = pillars

        parts.append('<div class="sstack">')
        for i, p in enumerate(pillar_list):
            if isinstance(p, str):
                continue
            pname = p.get("name", p.get("pillar", "Strategy"))
            pkey = p.get("key", pname.lower().replace(" ", "_"))
            summary = p.get("summary", "")
            items = p.get("details", p.get("items", []))
            if not isinstance(items, list):
                items = []

            type_cls = _pillar_type_class(pkey)
            pill_label = _pillar_pill(pkey)
            delay = f" d{i + 1}" if i < 6 else ""
            n_details = len(items)

            parts.append(f'<div class="sc {type_cls} sr{delay}">')
            parts.append(f'  <div class="sc-top" onclick="togSC(this)">')
            parts.append(f'    <div class="sc-bar"></div>')
            parts.append(f'    <div class="sc-body">')
            parts.append(f'      <div class="sc-pill">{pill_label}</div>')
            parts.append(f'      <div class="sc-tt" data-editable>{esc(pname)}</div>')
            parts.append(f'      <div class="sc-ds" data-editable>{esc(summary)}</div>')
            parts.append(f'    </div>')
            parts.append(f'    <div class="sc-met"><div class="sc-v">{n_details}</div><div class="sc-u">DETAILS</div></div>')
            parts.append(f'    <div class="sc-tog">{CHEVRON_SVG}</div>')
            parts.append(f'  </div>')
            parts.append(f'  <div class="sc-det"><div class="sc-det-in">')
            parts.append(f'    <div class="dg">')
            for item in items[:8]:
                if isinstance(item, str):
                    parsed = _parse_detail_bold(item)
                    match_obj = re.match(r'^<strong>(.+?)</strong>:?\s*(.*)', parsed)
                    if match_obj:
                        label = match_obj.group(1).upper()
                        value = match_obj.group(2) if match_obj.group(2) else parsed
                        parts.append(f'      <div class="di" data-editable><div class="di-l">{label}</div><div class="di-v">{value}</div></div>')
                    else:
                        parts.append(f'      <div class="di" data-editable><div class="di-l">DETAIL</div><div class="di-v">{parsed}</div></div>')
                elif isinstance(item, dict):
                    label = item.get("label", item.get("term", "DETAIL"))
                    detail = item.get("detail", item.get("description", ""))
                    parts.append(f'      <div class="di" data-editable><div class="di-l">{esc(label).upper()}</div><div class="di-v">{_parse_detail_bold(detail)}</div></div>')
            parts.append(f'    </div>')
            parts.append(f'  </div></div>')
            parts.append(f'</div>')

        parts.append('</div>')  # end .sstack

    return "\n".join(parts)


# ── Questions Tab ──

def build_questions_tab(data):
    """Build Questions tab with 14 standardized intake questions + pre-filled answers from synthesis."""
    s6 = data.get("s6", {})
    comp = data.get("s1", {}).get("company", {})
    company_name = comp.get("name", "")

    # Get pre-filled answers from synthesis (keyed by question number 1-11)
    prefilled = s6.get("intake_answers", {})

    parts = []

    parts.append('<div class="sl">INTAKE</div>')
    parts.append(f'<div class="sh" data-editable>Discovery Questions</div>')
    parts.append(f'<div class="sd" data-editable>14 questions to build a complete growth playbook for {esc(company_name)}.</div>')

    parts.append('<div class="q-s">')
    for i, question in enumerate(INTAKE_QUESTIONS):
        q_num = i + 1
        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        # Look up pre-filled answer
        answer = ""
        if isinstance(prefilled, dict):
            answer = prefilled.get(str(q_num), prefilled.get(f"q{q_num}", ""))
        if isinstance(answer, list):
            answer = " ".join(str(a) for a in answer)

        # Default placeholder text varies by question
        if q_num in (1, 2):
            default_text = "To be completed after playbook review"
        else:
            default_text = "To be completed after discovery call"

        answer_html = f'<div class="qa" data-editable>{esc(answer)}</div>' if answer else f'<div class="qa qa-empty" data-editable>{default_text}</div>'

        parts.append(
            f'<div class="qi sr{delay}" data-editable>'
            f'<div class="qn">{q_num}</div>'
            f'<div>'
            f'<div class="qt" data-editable>{esc(question)}</div>'
            f'{answer_html}'
            f'</div></div>'
        )
    parts.append('</div>')

    return "\n".join(parts)


# ── Opportunities Tab ──

def build_opportunities_tab(data):
    """Build opportunity cards using .opp pattern."""
    opps = data.get("s6", {}).get("creative_opportunities", [])
    if not opps:
        return '<p style="padding:20px;color:var(--ink-3)">No opportunities generated.</p>'

    border_colors = ["var(--sage)", "var(--blue)", "var(--peach)", "var(--steel)"]

    parts = []
    parts.append('<div class="sl">OPPORTUNITIES</div>')
    parts.append('<div class="sh">Creative Opportunities</div>')
    parts.append('<div class="sd">High-conviction growth moves synthesized from all intelligence.</div>')

    parts.append('<div class="opps">')
    for i, o in enumerate(opps):
        bc = border_colors[i % len(border_colors)]
        conf = o.get("confidence", 50)
        if isinstance(conf, str):
            try:
                conf = int(conf.replace("%", ""))
            except ValueError:
                conf = 50
        conf_cls = "conf-hi" if conf >= 65 else "conf-md"
        name = o.get("name", f"Opportunity {i + 1}")
        narrative = o.get("narrative", "")
        delay = f" d{i + 1}" if i < 6 else ""

        # Dependencies
        deps = o.get("dependencies", [])
        deps_html = ""
        if deps:
            deps_html = f'<div class="opp-deps"><div class="opp-dep-label">DEPENDENCIES</div>'
            for dep in deps:
                if isinstance(dep, dict):
                    dep_text = dep.get("dependency", dep.get("detail", dep.get("description", str(dep))))
                    source = dep.get("source", "")
                    deps_html += f'<div class="opp-dep"><strong>{esc(dep_text)}</strong>{": " + esc(source) if source else ""}</div>'
                else:
                    deps_html += f'<div class="opp-dep">{esc(str(dep))}</div>'
            deps_html += '</div>'

        # Executors / People
        executors = o.get("executors", o.get("people", []))
        people_html = ""
        if executors:
            people_html = '<div class="opp-people">'
            for ex in executors:
                if isinstance(ex, str):
                    # Get just the name part before ":"
                    ex_name = ex.split(":")[0].strip()
                    people_html += f'<span class="opp-tag">{esc(ex_name)}</span>'
                elif isinstance(ex, dict):
                    people_html += f'<span class="opp-tag">{esc(ex.get("name", ""))}</span>'
            people_html += '</div>'

        # Sequencing
        seq = o.get("sequencing", "")
        seq_html = ""
        if seq:
            seq_tags = []
            if isinstance(seq, str):
                # Parse "Unlocks" and "Needs" from sequencing text
                if "links to" in seq.lower() or "unlock" in seq.lower():
                    seq_tags.append(f'<span class="opp-seq-tag seq-unlocks">{esc(seq)}</span>')
                elif "must" in seq.lower() or "need" in seq.lower() or "after" in seq.lower():
                    seq_tags.append(f'<span class="opp-seq-tag seq-needs">{esc(seq)}</span>')
                else:
                    seq_tags.append(f'<span class="opp-seq-tag seq-unlocks">{esc(seq)}</span>')
            if seq_tags:
                seq_html = '<div class="opp-seq">' + "".join(seq_tags) + '</div>'

        # Current vs Activated
        cv = o.get("current_vs_activated", {})
        vs_html = ""
        if isinstance(cv, dict) and (cv.get("current") or cv.get("activated")):
            vs_html = (
                '<div class="opp-vs">'
                f'<div class="opp-vs-box vs-now"><div class="vs-label">CURRENT STATE</div>{esc(cv.get("current", ""))}</div>'
                f'<div class="opp-vs-box vs-then"><div class="vs-label">ACTIVATED STATE</div>{esc(cv.get("activated", ""))}</div>'
                '</div>'
            )

        # Metrics
        metrics = o.get("metrics", {})
        met_html = ""
        if isinstance(metrics, dict):
            met_items = []
            for mk, mv in metrics.items():
                label = mk.replace("_", " ").upper()
                val = str(mv) if mv else ""
                met_items.append(
                    f'<div class="opp-metric">'
                    f'<div class="opp-metric-n">{esc(val)}</div>'
                    f'<div class="opp-metric-l">{esc(label)}</div>'
                    f'</div>'
                )
            if met_items:
                met_html = '<div class="opp-metrics">' + "".join(met_items[:4]) + '</div>'
        elif isinstance(metrics, list):
            met_items = []
            for m in metrics[:4]:
                if isinstance(m, dict):
                    met_items.append(
                        f'<div class="opp-metric">'
                        f'<div class="opp-metric-n">{esc(m.get("value", ""))}</div>'
                        f'<div class="opp-metric-l">{esc(m.get("label", ""))}</div>'
                        f'</div>'
                    )
                else:
                    met_items.append(f'<div class="opp-metric"><div class="opp-metric-n">{esc(str(m))}</div></div>')
            if met_items:
                met_html = '<div class="opp-metrics">' + "".join(met_items) + '</div>'

        # Timeline
        timeline = o.get("timeline", o.get("execution_timeline", []))
        if not isinstance(timeline, list):
            timeline = []
        tl_html = ""
        if timeline:
            tl_items = ""
            for t in timeline[:6]:
                if isinstance(t, str):
                    # Try to split on ":" to get week/action
                    tparts = t.split(":", 1)
                    if len(tparts) == 2:
                        tl_items += f'<div class="opp-tl-item"><span class="opp-tl-wk">{esc(tparts[0].strip())}:</span> {esc(tparts[1].strip())}</div>'
                    else:
                        tl_items += f'<div class="opp-tl-item">{esc(t)}</div>'
                elif isinstance(t, dict):
                    tl_items += f'<div class="opp-tl-item"><span class="opp-tl-wk">{esc(t.get("period", t.get("week", "")))}</span> {esc(t.get("action", t.get("milestone", "")))}</div>'
            tl_html = f'<div class="opp-timeline"><div class="opp-tl-label">EXECUTION TIMELINE</div>{tl_items}</div>'

        # Confidence
        conf_reasoning = o.get("confidence_reasoning", "")
        conf_html = (
            f'<div class="opp-conf">'
            f'<div class="opp-conf-label">CONFIDENCE</div>'
            f'<div class="opp-conf-bar"><div class="opp-conf-fill {conf_cls}" style="width:{conf}%"></div></div>'
            f'<div class="opp-conf-note">{esc(conf_reasoning)}</div>'
            f'</div>'
        )

        # Assemble opportunity card
        parts.append(
            f'<div class="opp sr{delay}" onclick="togOpp(this)">'
            f'  <div class="opp-top" style="border-left-color:{bc}">'
            f'    <div class="opp-header">'
            f'      <div class="opp-title">{esc(name)}</div>'
            f'      <div class="opp-badge">{conf}% Confidence</div>'
            f'    </div>'
            f'    <div class="opp-summary">{esc(narrative[:250])}</div>'
            f'    <div class="opp-expand">{CHEVRON_SVG_12} Details</div>'
            f'  </div>'
            f'  <div class="opp-detail"><div class="opp-detail-inner"><div class="opp-cols">'
            f'    <div>'
            f'      <div class="opp-narrative">{esc(narrative)}</div>'
            f'      {people_html}'
            f'      {deps_html}'
            f'      {seq_html}'
            f'      {vs_html}'
            f'    </div>'
            f'    <div>'
            f'      {met_html}'
            f'      {tl_html}'
            f'      {conf_html}'
            f'    </div>'
            f'  </div></div></div>'
            f'</div>'
        )

    parts.append('</div>')  # end .opps
    return "\n".join(parts)


# ── Apollo contact helpers (concentric circles + contact cards) ──

def build_concentric_svg(concentric: dict, label: str) -> str:
    """Build inline SVG with 3 concentric rings + labels."""
    scanned = concentric.get("scanned", 0)
    targeted = concentric.get("targeted", 0)
    previewed = concentric.get("previewed", 0)

    def fmt(n):
        if n >= 1000:
            return f"{n:,}"
        return str(n)

    return (
        f'<div class="cc-wrap sr">'
        f'  <div class="cc-header">'
        f'    <div class="sl">CLIMATEDOOR INTELLIGENCE</div>'
        f'    <div class="sh">{esc(label)} Contact Search</div>'
        f'    <div class="sd">Matched from 275M+ B2B contact database. One contact per firm, ranked by relevance.</div>'
        f'  </div>'
        f'  <div class="cc-viz">'
        f'    <svg class="cc-svg" viewBox="0 0 320 320" xmlns="http://www.w3.org/2000/svg">'
        f'      <circle class="cc-ring cc-outer" cx="160" cy="160" r="150" />'
        f'      <circle class="cc-ring cc-mid" cx="160" cy="160" r="105" />'
        f'      <circle class="cc-ring cc-inner" cx="160" cy="160" r="60" />'
        f'      <text class="cc-num" x="160" y="155" text-anchor="middle" dominant-baseline="central">{fmt(previewed)}</text>'
        f'      <text class="cc-lbl" x="160" y="175" text-anchor="middle">previewed</text>'
        f'    </svg>'
        f'    <div class="cc-labels">'
        f'      <div class="cc-label-row"><span class="cc-dot cc-dot-outer"></span><span class="cc-label-n">{fmt(scanned)}</span> scanned</div>'
        f'      <div class="cc-label-row"><span class="cc-dot cc-dot-mid"></span><span class="cc-label-n">{fmt(targeted)}</span> highly targeted</div>'
        f'      <div class="cc-label-row"><span class="cc-dot cc-dot-inner"></span><span class="cc-label-n">{fmt(previewed)}</span> previewed below</div>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )


def _build_contact_card(c: dict, i: int, category: str, first_in_seg: bool = False) -> str:
    """Build a single Apollo contact card HTML."""
    ini = esc(c.get("initials", "?"))
    name = esc(c.get("display_name", ""))
    title = esc(c.get("title", ""))
    org = esc(c.get("organization_name", ""))
    fit = esc(c.get("fit_note", ""))
    loc_parts = [c.get("city", ""), c.get("state", "")]
    location = ", ".join([p for p in loc_parts if p])
    delay = f" d{(i % 6) + 1}" if i < 6 else ""
    first_cls = " apc-first" if first_in_seg else ""

    btn_primary = "Begin outreach" if category == "investors" else "Activate with Growth Pod"

    badge_html = ""
    ctype = c.get("type", "")
    if ctype == "named_target":
        badge_html = '<span class="apc-badge apc-named">NAMED TARGET</span>'
    elif ctype == "discovered":
        badge_html = '<span class="apc-badge apc-disc">DISCOVERED</span>'

    return (
        f'<div class="apc sr{delay}{first_cls}">'
        f'  {badge_html}'
        f'  <div class="apc-av">{ini}</div>'
        f'  <div class="apc-nm">{name}</div>'
        f'  <div class="apc-tt">{title}</div>'
        f'  <div class="apc-org">{org}</div>'
        + (f'  <div class="apc-loc">{esc(location)}</div>' if location else '')
        + (f'  <div class="apc-fit">{fit}</div>' if fit else '')
        + f'  <button class="apc-btn apc-btn-p">{btn_primary}</button>'
        f'</div>'
    )


def build_contact_cards(contacts: list, category: str, segments: list = None) -> str:
    """Build a continuous 3-col grid of Apollo contact cards with segment titles."""
    if segments:
        sorted_segs = sorted(
            [s for s in segments if s.get("contacts")],
            key=lambda s: len(s.get("contacts", [])),
            reverse=True,
        )
        parts = ['<div class="apc-grid">']
        card_idx = 0
        for seg_i, seg in enumerate(sorted_segs):
            seg_name = seg.get("segment_name", "")
            seg_contacts = seg.get("contacts", [])
            # Separator + full-width title (CSS hides first separator)
            parts.append('<hr class="apc-seg-sep">')
            parts.append(f'<div class="apc-seg-title">{esc(seg_name)}</div>')
            for j, c in enumerate(seg_contacts):
                parts.append(_build_contact_card(c, card_idx, category, first_in_seg=(j == 0)))
                card_idx += 1
        parts.append('</div>')
        return "\n".join(parts)

    # Flat layout (backward compatible / investors)
    if not contacts:
        return ""
    parts = ['<div class="apc-grid">']
    for i, c in enumerate(contacts):
        parts.append(_build_contact_card(c, i, category))
    parts.append('</div>')
    return "\n".join(parts)


# ── Investors Tab ──

def build_investors_tab(data):
    """Build investor cards using .inv pattern."""
    investors = data.get("s2", {}).get("investors", [])
    if not investors:
        return '<p style="padding:20px;color:var(--ink-3)">No investor matches.</p>'

    parts = []
    parts.append('<div class="sl">CAPITAL</div>')
    parts.append('<div class="sh">Investor Matches</div>')
    parts.append('<div class="sd">Qualified investors ranked by fit score across thesis, stage, geography, and relationship warmth.</div>')

    parts.append('<div class="inv-s"><div class="inv-list">')
    for i, inv in enumerate(investors[:20]):
        score = inv.get("score", 0)
        if isinstance(score, str):
            try:
                score = float(score)
            except ValueError:
                score = 0
        score_int = int(round(score))

        action = inv.get("action_level", "watch")
        # Ring class
        if score >= 80:
            ring_cls = "inv-hi"
        elif score >= 60:
            ring_cls = "inv-md"
        else:
            ring_cls = "inv-lo"

        # Action badge class
        action_map = {
            "act_now": "inv-act-now",
            "know": "inv-act-know",
            "watch": "inv-act-watch",
        }
        action_cls = action_map.get(action, "inv-act-watch")
        action_label = action.upper().replace("_", " ")

        name = inv.get("name", "")
        fund = inv.get("fund", "")
        check = inv.get("check_size", "")
        inv_type = inv.get("investor_type", "")
        # Build subtitle
        sub_parts = [s for s in [fund, check, inv_type] if s]
        subtitle = " | ".join(sub_parts)

        thesis = inv.get("thesis_summary", "")
        intro_path = inv.get("intro_path", {})
        if isinstance(intro_path, dict):
            intro_text = intro_path.get("detail", "")
            intro_type = intro_path.get("type", "cold")
        else:
            intro_text = str(intro_path)
            intro_type = "cold"
        approach = inv.get("approach", "")
        insights = inv.get("insights", [])
        conf_notes = inv.get("confidence_notes", "")

        # Map CD relationship owner based on warmth
        if intro_type == "warm":
            cd_owner = "Nick Findler"
        elif intro_type == "network":
            cd_owner = "Ash Kumar (BD)"
        else:
            cd_owner = "Ash Kumar (BD outreach)"

        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        # SVG score ring: circumference = 2*pi*20 = 125.66
        circ = 125.66
        offset = circ - (score / 100) * circ

        insights_html = ""
        for ins in insights:
            insights_html += f'<div class="inv-insight">{esc(ins)}</div>'

        conf_html = ""
        if conf_notes:
            conf_html = f'<div style="font-size:12px;color:var(--ink-4);margin-top:12px;font-style:italic">{esc(conf_notes)}</div>'

        parts.append(
            f'<div class="inv sr{delay}" onclick="togInv(this)">'
            f'  <div class="inv-top">'
            f'    <div class="inv-ring">'
            f'      <svg viewBox="0 0 48 48"><circle class="inv-ring-bg" cx="24" cy="24" r="20"/><circle class="inv-ring-fill {ring_cls}" cx="24" cy="24" r="20" stroke-dasharray="125.66" stroke-dashoffset="{offset:.1f}"/></svg>'
            f'      <div class="inv-ring-num">{score_int}</div>'
            f'    </div>'
            f'    <div class="inv-hd">'
            f'      <div class="inv-nm-line">'
            f'        <span class="inv-nm">{esc(name)}</span>'
            f'        <span class="inv-act {action_cls}">{action_label}</span>'
            f'      </div>'
            f'      <div class="inv-sub">{esc(subtitle)}</div>'
            f'    </div>'
            f'    <div class="inv-chev">+</div>'
            f'  </div>'
            f'  <div class="inv-detail">'
            f'    <div class="inv-narrative">{esc(thesis)}</div>'
            f'    <div class="inv-boxes">'
            f'      <div class="inv-box"><div class="inv-box-label lb-intro">INTRO PATH</div><div class="inv-box-text">{esc(intro_text)} Relationship owned by {esc(cd_owner)}.</div></div>'
            f'      <div class="inv-box"><div class="inv-box-label lb-approach">APPROACH</div><div class="inv-box-text">{esc(approach)}</div></div>'
            f'    </div>'
            f'    <div class="inv-insights">{insights_html}</div>'
            f'    {conf_html}'
            f'  </div>'
            f'</div>'
        )

    parts.append('</div></div>')  # end .inv-list .inv-s

    # Apollo investor contacts (step2b)
    s2b = data.get("s2b", {})
    inv_apollo = s2b.get("investors", {})
    inv_contacts = inv_apollo.get("contacts", [])
    if inv_contacts:
        inv_concentric = inv_apollo.get("concentric", {})
        parts.append(build_concentric_svg(inv_concentric, "Investor"))
        parts.append(build_contact_cards(inv_contacts, "investors"))

    return "\n".join(parts)


# ── Experts Tab ──

def build_experts_tab(data):
    """Build expert cards + Growth Pod using real CD team data."""
    s5 = data.get("s5", {})
    experts = s5.get("expert_matches", [])
    comp = data.get("s1", {}).get("company", {})
    company_name = comp.get("name", "")

    parts = []

    # Growth Pod section - use REAL CD team, not step5 pod assignments
    parts.append('<div class="sl">TEAM</div>')
    parts.append('<div class="sh">Growth Pod</div>')
    parts.append(f'<div class="sd">Your dedicated ClimateDoor team for the {esc(company_name)} engagement.</div>')

    # Select 5 team members relevant to this company
    # Nick always leads, then pick based on company needs
    pod_assignments = [
        {"key": "nick", "rationale": f"Lead all investor conversations for {esc(company_name)}. Activate Hot and Warm investor relationships from the 17 ACT NOW matches."},
        {"key": "sophie", "rationale": f"Build non-dilutive funding roadmap. Lead IRAP, SR&ED, and Investissement Quebec applications for {esc(company_name)}."},
        {"key": "ash", "rationale": f"Drive DSO and healthcare buyer outreach. Execute the Dentalcorp and 123Dentist procurement strategies."},
        {"key": "sam", "rationale": f"Coordinate client delivery and pipeline tracking. Manage the multi-stream playbook execution."},
        {"key": "tiff", "rationale": f"Lead Mi'gmaq community engagement in Gaspesie. Ensure community-first approach to Indigenous partnership opportunities."},
    ]

    parts.append('<div class="pod-s"><div class="pod-g">')
    for i, pa in enumerate(pod_assignments):
        tm = CD_TEAM.get(pa["key"], {})
        ini = initials(tm.get("name", ""))
        delay = f" d{i + 1}" if i < 6 else ""
        parts.append(
            f'<div class="pod sr{delay}">'
            f'  <div class="pod-i">{ini}</div>'
            f'  <div class="pod-nm">{esc(tm.get("name", ""))}</div>'
            f'  <div class="pod-tt">{esc(tm.get("role", ""))}</div>'
            f'  <div class="pod-fc">{pa["rationale"]}</div>'
            f'</div>'
        )
    parts.append('</div></div>')  # end .pod-g .pod-s

    # Note about full team
    parts.append('<div style="text-align:center;font-size:12px;color:var(--ink-3);margin-top:16px;font-weight:300">Full ClimateDoor team available: Chad Rickaby (Strategy), Jamie Moran (BD), Rizz Jiwani (Creative)</div>')

    # Expert Network section
    if experts:
        parts.append('<div class="sl" style="margin-top:48px">NETWORK</div>')
        parts.append('<div class="sh">Expert Network</div>')
        parts.append('<div class="sd">Subject matter experts matched to this engagement.</div>')

        parts.append('<div class="exp-s"><div class="exp-g">')
        for i, e in enumerate(experts):
            ename = e.get("name", "")
            title = e.get("title", "")
            location = e.get("location", "")
            agreement = e.get("agreement_status", "No")
            why = e.get("why_this_company", "")
            ini = initials(ename)
            delay = f" d{(i % 6) + 1}" if i < 6 else ""
            badge_text = "Agreement Signed" if agreement == "Yes" else "Pending Agreement"

            parts.append(
                f'<div class="exp sr{delay}">'
                f'  <div class="exp-av">{ini}</div>'
                f'  <div class="exp-nm">{esc(ename)}</div>'
                f'  <div class="exp-rl">{esc(title)}</div>'
                f'  <div class="exp-lc">{esc(location)}</div>'
                f'  <div class="exp-bd"><div class="exp-bdt"></div>{badge_text}</div>'
                f'  <div class="exp-why">{esc(why)}</div>'
                f'</div>'
            )
        parts.append('</div></div>')  # end .exp-g .exp-s

    return "\n".join(parts)


# ── Buyers Tab ──

def build_buyers_tab(data):
    """Build buyer segment cards using .sc pattern with .sc-sal class."""
    segments = data.get("s4", {}).get("buyer_segments", [])
    if not segments:
        return '<p style="padding:20px;color:var(--ink-3)">No buyer segments identified.</p>'

    parts = []
    parts.append('<div class="sl">SALES</div>')
    parts.append('<div class="sh">Buyer Segments</div>')
    parts.append('<div class="sd">Target buyer segments with named organizations, procurement structure, and ACV potential.</div>')

    parts.append('<div class="sstack">')
    for i, seg in enumerate(segments):
        seg_name = seg.get("segment_name", "")
        orgs = seg.get("named_organizations", [])
        dm = seg.get("decision_maker_title", "")
        procurement = seg.get("procurement_structure", "")
        cycle = seg.get("sales_cycle_estimate", "")
        acv = seg.get("acv_potential", "")
        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        # Build detail items
        di_items = []
        for org in orgs:
            if isinstance(org, dict):
                org_name = org.get("name", "")
                org_detail = org.get("detail", "")
                di_items.append(f'<div class="di"><div class="di-l">ORGANIZATION</div><div class="di-v"><strong>{esc(org_name)}</strong> {esc(org_detail)}</div></div>')
        if dm:
            di_items.append(f'<div class="di"><div class="di-l">DECISION MAKER</div><div class="di-v">{esc(dm)}</div></div>')
        if procurement:
            di_items.append(f'<div class="di"><div class="di-l">PROCUREMENT</div><div class="di-v">{esc(procurement)}</div></div>')
        if cycle:
            di_items.append(f'<div class="di"><div class="di-l">SALES CYCLE</div><div class="di-v">{esc(cycle)}</div></div>')
        if acv:
            di_items.append(f'<div class="di"><div class="di-l">ACV POTENTIAL</div><div class="di-v">{esc(safe_str(acv)[:500])}</div></div>')

        parts.append(
            f'<div class="sc sc-sal sr{delay}">'
            f'  <div class="sc-top" onclick="togSC(this)">'
            f'    <div class="sc-bar"></div>'
            f'    <div class="sc-body">'
            f'      <div class="sc-pill">BUYER SEGMENT</div>'
            f'      <div class="sc-tt">{esc(seg_name)}</div>'
            f'      <div class="sc-ds">{len(orgs)} named organizations</div>'
            f'    </div>'
            f'    <div class="sc-met"><div class="sc-v">{len(orgs)}</div><div class="sc-u">TARGETS</div></div>'
            f'    <div class="sc-tog">{CHEVRON_SVG}</div>'
            f'  </div>'
            f'  <div class="sc-det"><div class="sc-det-in">'
            f'    <div class="dg">'
            + "\n".join(di_items) +
            f'    </div>'
            f'  </div></div>'
            f'</div>'
        )

    parts.append('</div>')  # end .sstack

    # Apollo buyer contacts (step2b)
    s2b = data.get("s2b", {})
    buy_apollo = s2b.get("buyers", {})
    buy_contacts = buy_apollo.get("contacts", [])
    buy_segments = buy_apollo.get("segments", [])
    if buy_contacts or buy_segments:
        buy_concentric = buy_apollo.get("concentric", {})
        parts.append(build_concentric_svg(buy_concentric, "Buyer"))
        if buy_segments:
            parts.append(build_contact_cards(buy_contacts, "buyers", segments=buy_segments))
        else:
            parts.append(build_contact_cards(buy_contacts, "buyers"))

    return "\n".join(parts)


# ── Indigenous Tab ──

def build_indigenous_tab(data):
    """Build indigenous opportunity cards using .ind pattern with SVG score ring."""
    opps = data.get("s4", {}).get("indigenous_opportunities", [])
    if not opps:
        return '<p style="padding:20px;color:var(--ink-3)">No Indigenous partnership opportunities identified for this company.</p>'

    parts = []
    parts.append('<div class="sl">INDIGENOUS</div>')
    parts.append('<div class="sh">Indigenous Partnership Opportunities</div>')
    parts.append('<div class="sd">Community-first partnership opportunities identified through geographic and sector analysis.</div>')

    parts.append('<div class="ind-list">')
    for i, o in enumerate(opps):
        community = o.get("community_or_org", "")
        region = o.get("region", "")
        opp_type = o.get("opportunity_type", "")
        score = o.get("fit_score", 50)
        if isinstance(score, str):
            try:
                score = int(score)
            except ValueError:
                score = 50
        narrative = o.get("narrative", "")
        approach = o.get("approach", "")
        intro_path = o.get("intro_path", {})
        if isinstance(intro_path, dict):
            intro_text = intro_path.get("detail", "")
        else:
            intro_text = str(intro_path)
        grant_pathways = o.get("grant_pathways", [])
        action_level = o.get("action_level", "know")

        # SVG ring calculation: circumference = 2*pi*20 = 125.6
        circumference = 125.6
        offset = circumference * (1 - score / 100)

        # Badge class
        badge_map = {
            "act_now": "sig-badge-act",
            "know": "sig-badge-know",
            "watch": "sig-badge-watch",
        }
        badge_cls = badge_map.get(action_level, "sig-badge-know")
        badge_label = action_level.upper().replace("_", " ")

        subtitle = " · ".join([s for s in [region, opp_type] if s])
        delay = f" d{i + 1}" if i < 6 else ""

        grants_html = ""
        if grant_pathways:
            grants_text = ""
            for gp in grant_pathways:
                if isinstance(gp, str):
                    grants_text += esc(gp) + "<br>"
                elif isinstance(gp, dict):
                    grants_text += esc(gp.get("program", gp.get("name", ""))) + "<br>"
            grants_html = (
                f'<div class="ind-grants">'
                f'<div class="ind-grants-label">GRANT PATHWAYS</div>'
                f'<div class="ind-grants-text">{grants_text}</div>'
                f'</div>'
            )

        parts.append(
            f'<div class="ind sr{delay}">'
            f'  <div class="ind-top" onclick="togInd(this)">'
            f'    <div class="ind-score">'
            f'      <svg viewBox="0 0 48 48">'
            f'        <circle class="ind-score-bg" cx="24" cy="24" r="20"/>'
            f'        <circle class="ind-score-fill" cx="24" cy="24" r="20" stroke-dasharray="125.6" stroke-dashoffset="{offset:.1f}"/>'
            f'      </svg>'
            f'      <div class="ind-score-num">{score}</div>'
            f'    </div>'
            f'    <div class="ind-info">'
            f'      <div class="ind-name">{esc(community)}</div>'
            f'      <div class="ind-sub">{esc(subtitle)}</div>'
            f'    </div>'
            f'    <div class="ind-badge {badge_cls}">{badge_label}</div>'
            f'    <div class="ind-tog">{CHEVRON_SVG}</div>'
            f'  </div>'
            f'  <div class="ind-det"><div class="ind-det-in">'
            f'    <div class="ind-narrative">{esc(narrative)}</div>'
            f'    <div class="ind-boxes">'
            f'      <div class="ind-box"><div class="ind-box-label">APPROACH</div><div class="ind-box-text">{esc(approach)}</div></div>'
            f'      <div class="ind-box"><div class="ind-box-label">INTRO PATH</div><div class="ind-box-text">{esc(intro_text)}</div></div>'
            f'    </div>'
            f'    {grants_html}'
            f'  </div></div>'
            f'</div>'
        )

    parts.append('</div>')  # end .ind-list
    return "\n".join(parts)


# ── Grants Tab ──

def build_grants_tab(data):
    """Build grant cards using .sc pattern with .sc-gra class."""
    grants = data.get("s3", {}).get("direct_grants", [])
    # Sort by confidence, highest first
    def grant_conf(g):
        c = g.get("confidence", 0)
        if isinstance(c, float) and c <= 1:
            return c * 100
        return c if isinstance(c, (int, float)) else 0
    grants = sorted(grants, key=grant_conf, reverse=True)
    bd = data.get("s3", {}).get("grants_as_bd", [])

    parts = []
    parts.append('<div class="sl">NON-DILUTIVE</div>')
    parts.append('<div class="sh">Grant Opportunities</div>')
    parts.append('<div class="sd">Direct grant and tax credit opportunities matched to company profile.</div>')

    parts.append('<div class="sstack">')
    for i, g in enumerate(grants):
        program = g.get("program_name", "")
        agency = g.get("agency", "")
        amount = g.get("amount_range", "Unverified")
        fit = g.get("eligibility_fit", "moderate")
        intake = g.get("intake_status", "unknown")
        deadline = g.get("next_deadline", "")
        strategy = g.get("strategic_value", "")
        confidence = g.get("confidence", 0)
        if isinstance(confidence, float):
            confidence = int(confidence * 100)

        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        # Build detail items
        di_items = []
        if agency:
            di_items.append(f'<div class="di"><div class="di-l">AGENCY</div><div class="di-v">{esc(agency)}</div></div>')
        if amount:
            di_items.append(f'<div class="di"><div class="di-l">AMOUNT</div><div class="di-v">{esc(amount)}</div></div>')
        if intake:
            di_items.append(f'<div class="di"><div class="di-l">INTAKE STATUS</div><div class="di-v">{esc(intake)}</div></div>')
        if deadline:
            di_items.append(f'<div class="di"><div class="di-l">DEADLINE</div><div class="di-v">{esc(deadline)}</div></div>')
        if strategy:
            di_items.append(f'<div class="di"><div class="di-l">STRATEGIC VALUE</div><div class="di-v">{esc(strategy)}</div></div>')

        # Eligibility details
        elig = g.get("eligibility_details", [])
        for ed in elig[:4]:
            if isinstance(ed, dict):
                criterion = ed.get("criterion", "")
                met = ed.get("met")
                met_label = "Yes" if met is True else ("No" if met is False else "Unknown")
                di_items.append(f'<div class="di"><div class="di-l">ELIGIBILITY</div><div class="di-v"><strong>{esc(criterion)}</strong>: {met_label}</div></div>')

        conf_display = f"{confidence}%" if confidence else fit.upper()

        parts.append(
            f'<div class="sc sc-gra sr{delay}">'
            f'  <div class="sc-top" onclick="togSC(this)">'
            f'    <div class="sc-bar"></div>'
            f'    <div class="sc-body">'
            f'      <div class="sc-pill">GRANT</div>'
            f'      <div class="sc-tt">{esc(program)}</div>'
            f'      <div class="sc-ds">{esc(agency)}</div>'
            f'    </div>'
            f'    <div class="sc-met"><div class="sc-v">{conf_display}</div><div class="sc-u">CONFIDENCE</div></div>'
            f'    <div class="sc-tog">{CHEVRON_SVG}</div>'
            f'  </div>'
            f'  <div class="sc-det"><div class="sc-det-in">'
            f'    <div class="dg">'
            + "\n".join(di_items) +
            f'    </div>'
            f'  </div></div>'
            f'</div>'
        )
    parts.append('</div>')  # end .sstack

    # Grants-as-BD section
    if bd:
        parts.append('<div class="sl" style="margin-top:48px">BD TOOL</div>')
        parts.append('<div class="sh">Grants as Business Development</div>')
        parts.append('<div class="sd">Grant pathways that fund your customers to purchase your products.</div>')

        parts.append('<div class="sstack">')
        for i, b in enumerate(bd):
            program = b.get("grant_program", "")
            customer_type = b.get("customer_type", "")
            how = b.get("how_it_works", "")
            est_value = b.get("estimated_value", "")
            delay = f" d{(i % 6) + 1}" if i < 6 else ""

            di_items = []
            if customer_type:
                di_items.append(f'<div class="di"><div class="di-l">CUSTOMER TYPE</div><div class="di-v">{esc(customer_type)}</div></div>')
            if how:
                di_items.append(f'<div class="di"><div class="di-l">HOW IT WORKS</div><div class="di-v">{esc(how)}</div></div>')
            if est_value:
                di_items.append(f'<div class="di"><div class="di-l">ESTIMATED VALUE</div><div class="di-v">{esc(est_value)}</div></div>')

            parts.append(
                f'<div class="sc sc-gra sr{delay}">'
                f'  <div class="sc-top" onclick="togSC(this)">'
                f'    <div class="sc-bar"></div>'
                f'    <div class="sc-body">'
                f'      <div class="sc-pill">GRANTS AS BD</div>'
                f'      <div class="sc-tt">{esc(program)}</div>'
                f'      <div class="sc-ds">Customer: {esc(customer_type)}</div>'
                f'    </div>'
                f'    <div class="sc-tog">{CHEVRON_SVG}</div>'
                f'  </div>'
                f'  <div class="sc-det"><div class="sc-det-in">'
                f'    <div class="dg">'
                + "\n".join(di_items) +
                f'    </div>'
                f'  </div></div>'
                f'</div>'
            )
        parts.append('</div>')  # end .sstack

    return "\n".join(parts)


# ── Signals Tab ──

def build_signals_tab(data):
    """Build signal cards using .sig pattern in .sig-list."""
    signals = data.get("s4", {}).get("market_signals", [])
    if not signals:
        return '<p style="padding:20px;color:var(--ink-3)">No market signals identified.</p>'

    parts = []
    parts.append('<div class="sl">INTELLIGENCE</div>')
    parts.append('<div class="sh">Market Signals</div>')
    parts.append('<div class="sd">Real-time market intelligence relevant to growth strategy.</div>')

    parts.append('<div class="sig-s"><div class="sig-list">')
    for i, s in enumerate(signals):
        signal = s.get("signal", "")
        date = s.get("date", "")
        category = s.get("category", "")
        relevance = s.get("relevance", "")
        source_url = s.get("source_url", "")
        al = s.get("action_level", "watch")

        badge_map = {
            "act_now": "sig-badge-act",
            "know": "sig-badge-know",
            "watch": "sig-badge-watch",
        }
        badge_cls = badge_map.get(al, "sig-badge-watch")
        badge_label = al.upper().replace("_", " ")
        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        source_html = ""
        if source_url:
            source_html = f'<div class="sig-source"><a href="{esc(source_url)}" target="_blank">Source</a></div>'

        parts.append(
            f'<div class="sig sr{delay}">'
            f'  <div class="sig-top">'
            f'    <div class="sig-date">{esc(date)}</div>'
            f'    <div class="sig-badge {badge_cls}">{badge_label}</div>'
            f'  </div>'
            f'  <div class="sig-title">{esc(signal)}</div>'
            f'  <div class="sig-relevance">{esc(relevance)}</div>'
            f'  {source_html}'
            f'</div>'
        )

    parts.append('</div></div>')  # end .sig-list .sig-s
    return "\n".join(parts)


# ── Events Tab ──

def build_events_tab(data):
    """Build events tab using .evr cards."""
    events = data.get("s4", {}).get("conference_targets", [])
    if not events:
        return '<p style="padding:20px;color:var(--ink-3)">No conference targets identified.</p>'

    parts = []
    parts.append('<div class="sl">EVENTS</div>')
    parts.append('<div class="sh">Conference Targets</div>')
    parts.append('<div class="sd">Strategic events for market development and partnership building.</div>')

    parts.append('<div class="ev-s">')
    for i, ev in enumerate(events):
        ev_name = ev.get("event_name", "")
        ev_dates = ev.get("dates", "")
        ev_location = ev.get("location", "")
        ev_relevance = ev.get("relevance", "")
        fit_score = ev.get("fit_score", 50)
        if isinstance(fit_score, str):
            try:
                fit_score = int(fit_score)
            except ValueError:
                fit_score = 50

        ring_cls = "ev-h" if fit_score >= 70 else "ev-m"
        pr_cls = "ep-h" if fit_score >= 70 else "ep-m"
        pr_label = "HIGH FIT" if fit_score >= 70 else "MODERATE FIT"
        delay = f" d{(i % 6) + 1}" if i < 6 else ""

        date_loc = " · ".join([s for s in [ev_dates, ev_location] if s])

        parts.append(
            f'<div class="evr sr{delay}">'
            f'  <div class="ev-ring {ring_cls}">{fit_score}</div>'
            f'  <div class="ev-inf">'
            f'    <div class="ev-nm">{esc(ev_name)}</div>'
            f'    <div class="ev-dt">{esc(date_loc)}</div>'
            f'    <div class="ev-nt">{esc(ev_relevance[:200])}</div>'
            f'  </div>'
            f'  <div class="ev-pr {pr_cls}">{pr_label}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# ── Landscape Tab ──

def build_landscape_tab(data):
    """Build landscape tab with .comp-c for competitive position + .sc for competitors."""
    s4 = data.get("s4", {})
    s6 = data.get("s6", {})
    comps = s4.get("competitive_landscape", [])
    temp = s4.get("sector_temperature", {})
    comp_pos = s6.get("competitive_position", {})

    parts = []

    # Competitive Position (from synthesis)
    if comp_pos:
        parts.append('<div class="sl">DEFENSIBILITY</div>')
        parts.append('<div class="sh">Competitive Position</div>')
        parts.append('<div class="sd">Structural advantages and defensibility assessment.</div>')

        parts.append('<div class="comp-s sr">')
        parts.append('<div class="comp-c">')
        parts.append(f'<div class="comp-ch">{SHIELD_SVG} COMPETITIVE POSITION</div>')

        intro = comp_pos.get("intro", comp_pos.get("summary", ""))
        if intro:
            parts.append(f'<div class="comp-intro">{esc(intro)}</div>')

        factors = comp_pos.get("defensibility_factors", comp_pos.get("factors", []))
        if factors:
            parts.append('<div class="comp-factors">')
            for fi, f in enumerate(factors):
                if isinstance(f, dict):
                    factor_name = f.get("factor", f.get("name", ""))
                    evidence = f.get("evidence", f.get("detail", ""))
                else:
                    factor_name = str(f)
                    evidence = ""
                parts.append(
                    f'<div class="comp-factor">'
                    f'<div class="comp-factor-hdr">'
                    f'<div class="comp-factor-num">{fi + 1}</div>'
                    f'<div class="comp-factor-title">{esc(factor_name)}</div>'
                    f'</div>'
                    f'<div class="comp-factor-text">{esc(evidence)}</div>'
                    f'</div>'
                )
            parts.append('</div>')

        risk = comp_pos.get("primary_risk", "")
        mitigant = comp_pos.get("risk_mitigant", "")
        if risk:
            parts.append(
                f'<div class="comp-risk">'
                f'<div class="comp-risk-label">PRIMARY RISK</div>'
                f'<div class="comp-risk-text">{esc(risk)}'
                f'{". Mitigant: " + esc(mitigant) if mitigant else ""}'
                f'</div></div>'
            )

        parts.append('</div>')  # end .comp-c
        parts.append('</div>')  # end .comp-s

    # Sector Temperature
    if temp:
        assess = temp.get("assessment", "?")
        evidence = temp.get("evidence", [])
        parts.append(f'<div class="sl" style="margin-top:48px">SECTOR</div>')
        parts.append(f'<div class="sh">Sector Temperature: {esc(assess.title())}</div>')
        parts.append(f'<div class="sd">Market momentum indicators and policy direction.</div>')

        parts.append('<div class="sstack">')
        for i, ev in enumerate(evidence):
            if isinstance(ev, dict):
                data_point = ev.get("data_point", "")
                ev_date = ev.get("date", "")
                ev_source = ev.get("source_url", "")
            else:
                data_point = str(ev)
                ev_date = ""
                ev_source = ""
            delay = f" d{(i % 6) + 1}" if i < 6 else ""
            parts.append(
                f'<div class="sc sc-mkt sr{delay}">'
                f'  <div class="sc-top" onclick="togSC(this)">'
                f'    <div class="sc-bar"></div>'
                f'    <div class="sc-body">'
                f'      <div class="sc-pill">EVIDENCE</div>'
                f'      <div class="sc-tt">{esc(data_point[:120])}</div>'
                f'      <div class="sc-ds">{esc(ev_date)}</div>'
                f'    </div>'
                f'    <div class="sc-tog">{CHEVRON_SVG}</div>'
                f'  </div>'
                f'  <div class="sc-det"><div class="sc-det-in">'
                f'    <div class="dg">'
                f'      <div class="di"><div class="di-l">DETAIL</div><div class="di-v">{esc(data_point)}</div></div>'
                + (f'      <div class="di"><div class="di-l">SOURCE</div><div class="di-v"><a href="{esc(ev_source)}" target="_blank">{esc(ev_source[:80])}</a></div></div>' if ev_source else '') +
                f'    </div>'
                f'  </div></div>'
                f'</div>'
            )
        parts.append('</div>')

    # Competitive Landscape
    if comps:
        parts.append(f'<div class="sl" style="margin-top:48px">COMPETITORS</div>')
        parts.append(f'<div class="sh">Competitive Landscape</div>')
        parts.append(f'<div class="sd">Direct and adjacent competitors with differentiation analysis.</div>')

        parts.append('<div class="sstack">')
        for i, c in enumerate(comps):
            cname = c.get("company_name", "")
            desc = c.get("description", "")
            diff = c.get("differentiator_vs_frett", "")
            strengths = c.get("strengths", "")
            weaknesses = c.get("weaknesses", "")
            trl = c.get("trl", "")
            funding = c.get("funding_known", "")
            delay = f" d{(i % 6) + 1}" if i < 6 else ""

            di_items = []
            if desc:
                di_items.append(f'<div class="di"><div class="di-l">DESCRIPTION</div><div class="di-v">{esc(desc)}</div></div>')
            if diff:
                di_items.append(f'<div class="di"><div class="di-l">VS COMPANY</div><div class="di-v">{esc(diff)}</div></div>')
            if strengths:
                di_items.append(f'<div class="di"><div class="di-l">STRENGTHS</div><div class="di-v">{esc(strengths)}</div></div>')
            if weaknesses:
                di_items.append(f'<div class="di"><div class="di-l">WEAKNESSES</div><div class="di-v">{esc(weaknesses)}</div></div>')

            parts.append(
                f'<div class="sc sc-mkt sr{delay}">'
                f'  <div class="sc-top" onclick="togSC(this)">'
                f'    <div class="sc-bar"></div>'
                f'    <div class="sc-body">'
                f'      <div class="sc-pill">COMPETITOR</div>'
                f'      <div class="sc-tt">{esc(cname)}</div>'
                f'      <div class="sc-ds">TRL {trl} | {esc(funding[:80]) if funding else "Funding unknown"}</div>'
                f'    </div>'
                f'    <div class="sc-tog">{CHEVRON_SVG}</div>'
                f'  </div>'
                f'  <div class="sc-det"><div class="sc-det-in">'
                f'    <div class="dg">'
                + "\n".join(di_items) +
                f'    </div>'
                f'  </div></div>'
                f'</div>'
            )
        parts.append('</div>')

    return "\n".join(parts)


# ── Main assembly ───────────────────────────────────────

def assemble(slug: str) -> Path:
    data = load_data(slug)
    with open(TEMPLATE_PATH) as f:
        tpl = f.read()

    comp = data.get("s1", {}).get("company", {})
    c = counts(data)
    s2_stats = data.get("s2", {}).get("pipeline_stats", {})

    # Split company name for hero styling
    name = comp.get("name", slug.replace("-", " ").title())
    name_parts = name.rsplit(" ", 1)
    first = name_parts[0] if len(name_parts) > 1 else name
    last = name_parts[1] if len(name_parts) > 1 else ""

    # Build pillar subtitles
    top_inv = data.get("s2", {}).get("investors", [{}])[0] if data.get("s2", {}).get("investors") else {}
    strong_grants = data.get("s3", {}).get("pipeline_stats", {}).get("strong_fit", 0)

    # Founder name for "Prepared for"
    team_data = data.get("s1", {}).get("team", {})
    founders = team_data.get("founders", []) if isinstance(team_data, dict) else []
    prepared_for = founders[0].get("name", name) if founders else name

    replacements = {
        "{{COMPANY_NAME}}": esc(name),
        "{{PHASE}}": "1",
        "{{HERO_COMPANY_FIRST}}": esc(first),
        "{{HERO_COMPANY_LAST}}": esc(last),
        "{{COMPANY_DESCRIPTION}}": esc(comp.get("description", "")),
        "{{HERO_TAGS}}": build_hero_tags(data),
        "{{PREPARED_FOR}}": esc(prepared_for),
        "{{GENERATION_DATE}}": datetime.now().strftime("%B %d, %Y"),
        "{{DISCOVERY_TOTAL}}": str(c["total"]),
        "{{COUNT_INVESTORS}}": str(c["investors"]),
        "{{COUNT_GRANTS}}": str(c["grants"]),
        "{{COUNT_SEGMENTS}}": str(c["segments"]),
        "{{COUNT_SIGNALS}}": str(c["signals"]),
        "{{COUNT_OPPORTUNITIES}}": str(c["opportunities"]),
        "{{COUNT_EXPERTS}}": str(c["experts"]),
        "{{COUNT_INDIGENOUS}}": str(c["indigenous"]),
        "{{COUNT_EVENTS}}": str(c["events"]),
        "{{PILLAR_CAPITAL_SUB}}": f"Top: {esc(top_inv.get('name', ''))} ({top_inv.get('score', 0):.0f})" if top_inv.get("name") else "See matches",
        "{{PILLAR_GRANTS_SUB}}": f"{strong_grants} strong fit programs",
        "{{PILLAR_SALES_SUB}}": f"{c['segments']} buyer segments mapped",
        "{{PILLAR_SIGNALS_SUB}}": f"{c['signals']} signals tracked",
        "{{ALERTS_HTML}}": build_alerts(data),
        "{{OVERVIEW_TAB_CONTENT}}": build_overview_tab(data),
        "{{QUESTIONS_TAB_CONTENT}}": build_questions_tab(data),
        "{{OPPORTUNITIES_TAB_CONTENT}}": build_opportunities_tab(data),
        "{{INVESTORS_TAB_CONTENT}}": build_investors_tab(data),
        "{{EXPERTS_TAB_CONTENT}}": build_experts_tab(data),
        "{{BUYERS_TAB_CONTENT}}": build_buyers_tab(data),
        "{{INDIGENOUS_TAB_CONTENT}}": build_indigenous_tab(data),
        "{{GRANTS_TAB_CONTENT}}": build_grants_tab(data),
        "{{SIGNALS_TAB_CONTENT}}": build_signals_tab(data),
        "{{EVENTS_TAB_CONTENT}}": build_events_tab(data),
        "{{LANDSCAPE_TAB_CONTENT}}": build_landscape_tab(data),
        "{{STAT_INVESTORS_SCANNED}}": str(s2_stats.get("db_total_records", 2645)),
        "{{STAT_STAGE_MATCH}}": str(s2_stats.get("pass2_stage_geography", 0)),
        "{{STAT_SECTOR_MATCH}}": str(s2_stats.get("pass1_direct_sector", 0)),
        "{{STAT_REGION_MATCH}}": str(s2_stats.get("unique_after_merge", 0)),
        "{{STAT_GRANTS_SCANNED}}": str(c["grants"]),
        "{{STAT_EXPERTS_MATCHED}}": str(c["experts"]),
        "{{STAT_PAGES_CRAWLED}}": str(data.get("s1", {}).get("generation_metadata", {}).get("website_pages_crawled", 0)),
    }

    out = tpl
    for slot, val in replacements.items():
        out = out.replace(slot, str(val))

    output_path = SKILL_ROOT / "data" / slug / "playbook.html"
    with open(output_path, 'w') as f:
        f.write(out)

    print(f"{'=' * 60}")
    print(f"STEP 7: HTML Assembly")
    print(f"  Company: {name}")
    print(f"  Discoveries: {c['total']}")
    print(f"    Investors:{c['investors']} Grants:{c['grants']} Segments:{c['segments']} Signals:{c['signals']}")
    print(f"    Opportunities:{c['opportunities']} Experts:{c['experts']} Indigenous:{c['indigenous']} Events:{c['events']}")
    print(f"  Output: {output_path}")
    print(f"  Size: {output_path.stat().st_size:,} bytes")
    print(f"{'=' * 60}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step7_assemble.py <slug>")
        sys.exit(1)
    assemble(sys.argv[1])
