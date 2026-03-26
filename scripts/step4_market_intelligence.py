#!/usr/bin/env python3
"""
Step 4: Market Intelligence (Self-Contained)
Model: Sonnet with web search tool
Input: data/[slug]/step1-company.json
Output: data/[slug]/step4-market.json

Self-contained market research:
  1. Read company profile from step1-company.json
  2. Web search for buyers, competitors, signals, conferences, indigenous angles, market sizing
  3. Sonnet structures all research into step4-market.json

CRITICAL: Every market sizing number needs a cited source or shown math.
"""

import json
import os

# Load API keys from .env files
for env_file in ["/home/openclaw/radar-platform/.env", "/home/openclaw/.openclaw/workspace-bd/.env"]:
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
import sys
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

SONNET_MODEL = "claude-sonnet-4-6"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")


# ---------------------------------------------------------------------------
# Web research via Anthropic API
# ---------------------------------------------------------------------------

def run_market_web_research(client: anthropic.Anthropic, company: dict) -> str:
    """Use Sonnet with web search to do comprehensive market research."""
    comp = company.get("company", {})
    product = company.get("product", {})
    market = company.get("market", {})
    geo = comp.get("geography", {})

    hq = geo.get("hq", "Canada")
    sector = comp.get("sector", "cleantech")
    sub_sector = comp.get("sub_sector", "")
    product_desc = product.get("description", comp.get("description", ""))
    target_buyers = market.get("target_buyers", [])
    company_name = comp.get("name", "")

    search_prompt = f"""Do comprehensive market research for this company. Search the web thoroughly.

Company: {company_name}
Sector: {sector} / {sub_sector}
Product: {product_desc[:500]}
Target Buyers: {json.dumps(target_buyers)}
HQ: {hq}

I need you to search for ALL of the following:

1. BUYERS: Search for "{product_desc[:50]} buyers Canada", "{sector} procurement", "largest {sub_sector or sector} companies Canada"
   - Find specific named organizations that would buy this product
   - Find decision maker titles and procurement structures

2. COMPETITORS: Search for "{product_desc[:50]} competitors", "{company_name} vs", "{sub_sector or sector} startups 2025 2026"
   - Find actual competitor companies with websites
   - Note their funding, TRL, differentiators

3. MARKET SIGNALS: Search for "{sector} regulation 2026", "{sector} policy Canada", "{sector} market trend 2025 2026"
   - Find specific regulatory changes, policy announcements
   - Note dates and sources

4. CONFERENCES: Search for "{sector} conference 2026 Canada", "{sub_sector or sector} trade show 2026"
   - Only events AFTER March 2026
   - Get dates, locations, registration URLs

5. INDIGENOUS ANGLES: Search for "{product_desc[:30]} indigenous community", "{sector} First Nations Canada"
   - Find relevant programs, partnerships, procurement opportunities
   - Community-first approach required

6. MARKET SIZING: Search for "{sector} market size", "{sub_sector or sector} TAM", "{sector} market report 2025 2026"
   - Find TAM/SAM/SOM data with cited sources
   - Show math for any calculations

For each piece of information, include the source URL. Be thorough - use multiple searches.
Return ALL raw findings organized by category."""

    print(f"  Running comprehensive market web research...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=12000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 15}],
        messages=[{"role": "user", "content": search_prompt}],
    )
    elapsed = time.time() - t0

    text_parts = []
    search_count = 0
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            text_parts.append(block.text)
        if block.type == 'server_tool_use':
            search_count += 1

    result = "\n".join(text_parts)
    print(f"  Web research complete in {elapsed:.1f}s ({search_count} searches, {response.usage.input_tokens}in/{response.usage.output_tokens}out)")
    return result


# ---------------------------------------------------------------------------
# Sonnet structured analysis
# ---------------------------------------------------------------------------

MARKET_SYSTEM = """You are a market intelligence analyst for ClimateDoor, a climate venture advisory firm.
You are producing structured market intelligence for a company playbook.

CRITICAL SOURCING RULES:
1. Every market sizing number MUST have: a cited source with URL, a calculation with shown methodology, or an explicit "unverified" flag.
2. Named organizations, not categories. "Dentalcorp (500+ clinics)" not "large DSOs".
3. Decision maker titles from actual org charts or job postings, not generic guesses.
4. Conference dates must be from event websites. Do not include events that have already happened (today is {today}).
5. Competitors must actually exist - provide website URLs.
6. For sector temperature: cite specific evidence from the last 6 months.

For Indigenous partnership opportunities:
- Community-first engagement is mandatory.
- Local employment and capacity building must be part of any deployment approach.
- Revenue/benefit sharing where applicable.
- Let the community decide scope and pace.

Output valid JSON only. No markdown fences."""


def run_market_analysis(client: anthropic.Anthropic, company: dict, web_research: str) -> dict:
    """Structure all market research into the step4 JSON schema."""
    comp = company.get("company", {})
    product = company.get("product", {})
    traction = company.get("traction", {})
    market = company.get("market", {})

    company_summary = {
        "name": comp.get("name", ""),
        "description": comp.get("description", ""),
        "sector": comp.get("sector", ""),
        "sub_sector": comp.get("sub_sector", ""),
        "stage": comp.get("stage", ""),
        "trl": comp.get("trl", ""),
        "geography": comp.get("geography", {}),
        "product": product.get("description", ""),
        "key_claims": [c.get("claim", "") for c in product.get("key_claims", [])[:5]],
        "regulatory": {k: v.get("status", "") for k, v in product.get("regulatory_status", {}).items()},
        "patents": [p.get("title", "") for p in product.get("ip", {}).get("patents", [])],
        "target_buyers": market.get("target_buyers", []),
        "website_logos": [l.get("name", "") for l in traction.get("website_logos", [])],
        "recent_news": [n.get("headline", "") for n in company.get("signals", {}).get("recent_news", [])],
        "data_gaps": company.get("data_gaps", [])[:5],
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    user_msg = f"""Produce a complete market intelligence analysis using ALL the web research data below.

COMPANY PROFILE:
{json.dumps(company_summary, indent=2)}

WEB RESEARCH DATA:
{web_research[:50000]}

Output a single JSON object with these sections:

1. "buyer_segments": array of 3-5 objects, each with:
   - segment_name, named_organizations (array of {{name, detail, source_url}}),
   - decision_maker_title, procurement_structure, sales_cycle_estimate,
   - acv_potential (with SHOWN MATH), acv_source

2. "market_signals": array of 3-6 objects, each with:
   - signal (specific, dated), category (regulatory|competitive|procurement|market),
   - date, source_url, relevance (1-2 sentences),
   - action_level (act_now|know|watch), time_sensitivity

3. "competitive_landscape": array of 3-5 objects, each with:
   - company_name, website_url, description, differentiator_vs_subject,
   - strengths, weaknesses, trl, funding_known (with source or "unknown"),
   - market_position

4. "conference_targets": array of 3-5 objects, each with:
   - event_name, dates, location, source_url, attendee_count,
   - registration_status, relevance, fit_score (0-100)
   IMPORTANT: Only include events AFTER {today}.

5. "indigenous_opportunities": array of 0-3 objects, each with:
   - community_or_org, region, opportunity_type,
   - fit_score (0-100), narrative (3-5 sentences),
   - approach (community-first strategy), grant_pathways, action_level

6. "sector_temperature": object with:
   - assessment (hot|warming|stable|cooling|cold),
   - evidence (array of specific data points with dates and sources),
   - competitor_funding (array of {{competitor, round, amount, date, source_url}}),
   - policy_direction (supportive|neutral|hostile with evidence)

7. "market_sizing": object with:
   - tam, sam, som (each with source or shown math),
   - methodology_note

Output ONLY the JSON object."""

    print(f"  Calling Sonnet for structured market analysis...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=16000,
        system=MARKET_SYSTEM.format(today=today),
        messages=[{"role": "user", "content": user_msg}],
    )
    elapsed = time.time() - t0
    raw = response.content[0].text.strip()
    print(f"  Sonnet responded in {elapsed:.1f}s ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")

    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        depth = 0
        start = raw.index('{')
        for i in range(start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except json.JSONDecodeError:
                        continue
        print(f"  [ERROR] Failed to parse Sonnet market JSON")
        return {"error": "parse_failed", "raw": raw[:2000]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_step4(slug: str) -> Path:
    data_dir = SKILL_ROOT / "data" / slug
    step1_path = data_dir / "step1-company.json"
    output_path = data_dir / "step4-market.json"

    if not step1_path.exists():
        print(f"ERROR: {step1_path} not found. Run Step 1 first.")
        sys.exit(1)

    with open(step1_path) as f:
        company = json.load(f)

    comp = company.get("company", {})
    print(f"=" * 60)
    print(f"STEP 4: Market Intelligence (Self-Contained)")
    print(f"Company: {comp.get('name', 'Unknown')}")
    print(f"Sector:  {comp.get('sector', 'Unknown')}")
    print(f"Output:  {output_path}")
    print(f"=" * 60)

    client = anthropic.Anthropic()

    # Phase 1: Web research
    print(f"\n[Phase 1] Running comprehensive web research...")
    web_research = run_market_web_research(client, company)

    # Phase 2: Structured analysis
    print(f"\n[Phase 2] Running structured market analysis...")
    result = run_market_analysis(client, company, web_research)

    if "error" in result:
        print(f"  [WARN] Market analysis had errors, saving partial result")

    output = {
        "company": comp.get("name", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": SONNET_MODEL,
        **result,
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"STEP 4 COMPLETE")
    print(f"  Output: {output_path}")
    if "buyer_segments" in result:
        print(f"  Buyer segments: {len(result.get('buyer_segments', []))}")
    if "market_signals" in result:
        signals = result.get("market_signals", [])
        act = sum(1 for s in signals if s.get("action_level") == "act_now")
        print(f"  Market signals: {len(signals)} ({act} ACT NOW)")
    if "competitive_landscape" in result:
        print(f"  Competitors: {len(result.get('competitive_landscape', []))}")
    if "conference_targets" in result:
        print(f"  Conference targets: {len(result.get('conference_targets', []))}")
    if "indigenous_opportunities" in result:
        print(f"  Indigenous opportunities: {len(result.get('indigenous_opportunities', []))}")
    if "sector_temperature" in result:
        print(f"  Sector temperature: {result.get('sector_temperature', {}).get('assessment', '?')}")
    if "market_sizing" in result:
        print(f"  Market sizing: TAM={result.get('market_sizing', {}).get('tam', '?')}")
    print(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step4_market_intelligence.py <company-slug>")
        print("Example: python3 step4_market_intelligence.py fuse-power")
        sys.exit(1)

    slug = sys.argv[1]
    output = run_step4(slug)
    print(f"\nDone. Output at: {output}")
