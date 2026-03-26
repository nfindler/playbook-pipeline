#!/usr/bin/env python3
"""
Step 2: Multi-Pass Investor Matching
Model: Sonnet (reasoning for thesis analysis + web verification)
Input: data/[slug]/step1-company.json + investor SQLite DB (2,645 contacts)
Output: data/[slug]/step2-investors.json

Architecture: 5 separate query passes, merge + de-duplicate, 6-factor weighted
scoring, then Sonnet evaluates top candidates and web-verifies top 15.

Read references/investor-scoring.md for full methodology.
"""

import json
import os
import sys
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SONNET_MODEL = "claude-sonnet-4-6"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")
INVESTOR_DB = Path("/home/openclaw/radar-platform/data/investors.db")

# Actual industry_preferred terms in the DB (not the ICP v7 picklist)
DB_INDUSTRY_TERMS = [
    "AI", "Advanced Materials & Manufacturing", "Agriculture & Forestry",
    "Batteries & Storage", "Carbon Solutions", "Circular Economy",
    "Climate / Cleantech General", "Construction & Green Buildings",
    "Consumer Products", "Deep Tech", "Education", "Energy & Renewables",
    "Finance & Insurance", "Food & Beverage", "Healthcare", "Hydrogen",
    "Marine & Ocean Tech", "Mining & Minerals", "Oil & Gas",
    "Recycling & Waste", "Software & Digital Solutions",
    "Transportation & Mobility", "Water",
]

# Map ICP v7 primary sectors -> DB industry_preferred terms for direct match
SECTOR_TO_DB_TERMS = {
    "Circular Economy": ["Circular Economy", "Recycling & Waste", "Consumer Products"],
    "Ag & Food": ["Agriculture & Forestry", "Food & Beverage"],
    "Energy & Storage": ["Energy & Renewables", "Batteries & Storage", "Hydrogen"],
    "Buildings & Smart Cities": ["Construction & Green Buildings", "Energy & Renewables"],
    "Carbon": ["Carbon Solutions", "Energy & Renewables"],
    "Transportation": ["Transportation & Mobility", "Energy & Renewables"],
    "Water & Decontamination": ["Water", "Marine & Ocean Tech"],
    "Clean Industry / Advanced Manufacturing": ["Advanced Materials & Manufacturing", "Circular Economy"],
    "Climate Intelligence & Software": ["Software & Digital Solutions", "AI", "Climate / Cleantech General"],
    "Nature-based & Community Solutions": ["Agriculture & Forestry", "Carbon Solutions", "Water"],
    "Digital Services": ["Software & Digital Solutions", "AI"],
    "Finance Policy & Markets": ["Finance & Insurance"],
    "Other": ["Climate / Cleantech General"],
}

# Adjacent sector map (from investor-scoring.md, translated to DB terms)
ADJACENT_SECTORS = {
    "Circular Economy": ["Advanced Materials & Manufacturing", "Consumer Products", "Construction & Green Buildings", "Healthcare"],
    "Ag & Food": ["Water", "Marine & Ocean Tech", "Food & Beverage"],
    "Energy & Storage": ["Advanced Materials & Manufacturing", "Transportation & Mobility", "Construction & Green Buildings"],
    "Buildings & Smart Cities": ["Energy & Renewables", "Software & Digital Solutions"],
    "Carbon": ["Energy & Renewables", "Agriculture & Forestry"],
    "Transportation": ["Energy & Renewables", "Software & Digital Solutions", "Advanced Materials & Manufacturing"],
    "Water & Decontamination": ["Agriculture & Forestry", "Marine & Ocean Tech"],
    "Clean Industry / Advanced Manufacturing": ["Circular Economy", "Energy & Renewables", "Recycling & Waste"],
    "Climate Intelligence & Software": DB_INDUSTRY_TERMS,  # horizontal play
    "Nature-based & Community Solutions": ["Agriculture & Forestry", "Water", "Carbon Solutions"],
    "Digital Services": ["Software & Digital Solutions", "AI", "Climate / Cleantech General"],
    "Finance Policy & Markets": ["Software & Digital Solutions", "Climate / Cleantech General"],
    "Other": ["Climate / Cleantech General"],
}

# Map DB warmth values to intro warmth scores
WARMTH_SCORES = {
    "Already Invested": 98,
    "Hot": 92,
    "Personal": 88,
    "Met in person": 85,
    "Warm": 80,
    "Connected Online": 60,
    "Target": 35,
    "Cold": 25,
    "": 15,
    None: 15,
}

# Map DB cheque_size to numeric ranges for stage fit calc
CHEQUE_RANGES = {
    "$0-$100K": (0, 100_000),
    "$100k-$1M": (100_000, 1_000_000),
    "$1M-$5M": (1_000_000, 5_000_000),
    "$5M+": (5_000_000, 50_000_000),
    "": (0, 0),
    None: (0, 0),
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(INVESTOR_DB))
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Pass 1: Direct Sector Match
# ---------------------------------------------------------------------------

def pass1_direct_sector(conn: sqlite3.Connection, company: dict) -> list[dict]:
    """Query investors whose industry_preferred matches the company's sector."""
    sector = company.get("company", {}).get("sector", "Other")
    sub_sector = company.get("company", {}).get("sub_sector", "")

    # Get the DB terms for this sector
    db_terms = SECTOR_TO_DB_TERMS.get(sector, ["Climate / Cleantech General"])

    # Also add sub-sector keyword matches
    sub_keywords = []
    if sub_sector:
        # Extract keywords from sub-sector like "Sustainable Fashion & Medical Textiles"
        for word in re.split(r'[&,/\s]+', sub_sector):
            word = word.strip()
            if len(word) > 3:
                sub_keywords.append(word)

    # Build WHERE clause
    conditions = []
    params = []
    for term in db_terms:
        conditions.append("industry_preferred LIKE ?")
        params.append(f"%{term}%")
    for kw in sub_keywords:
        # Check if keyword matches any DB industry term
        for db_term in DB_INDUSTRY_TERMS:
            if kw.lower() in db_term.lower():
                conditions.append("industry_preferred LIKE ?")
                params.append(f"%{db_term}%")

    if not conditions:
        return []

    where = " OR ".join(conditions)
    sql = f"""
        SELECT * FROM investors
        WHERE ({where})
          AND investor_type NOT LIKE '%Broker%'
          AND investor_type NOT LIKE '%Pubco%'
    """

    cursor = conn.execute(sql, params)
    results = rows_to_dicts(cursor.fetchall())
    print(f"  Pass 1 (Direct Sector): {len(results)} investors for terms {db_terms}")
    return results


# ---------------------------------------------------------------------------
# Pass 2: Stage + Geography Match
# ---------------------------------------------------------------------------

def pass2_stage_geography(conn: sqlite3.Connection, company: dict) -> list[dict]:
    """Stage + geography match regardless of sector. Catches active generalists."""
    stage = company.get("company", {}).get("stage", "")
    geo = company.get("company", {}).get("geography", {})
    country = "Canada"  # Frett is in Quebec, Canada
    if geo.get("hq"):
        hq = geo["hq"]
        if "Canada" in hq or "Quebec" in hq:
            country = "Canada"
        elif "United States" in hq or "US" in hq:
            country = "USA"

    # Map company stage to DB stage_preferred terms
    stage_terms = []
    if stage in ("Growth", "Series C+"):
        stage_terms = ["Series B", "Series C+", "Mezzanine"]
    elif stage == "Series B":
        stage_terms = ["Series A", "Series B", "Series C+"]
    elif stage == "Series A":
        stage_terms = ["Seed", "Series A", "Series B"]
    elif stage == "Seed":
        stage_terms = ["Pre-seed", "Seed", "Series A"]
    elif stage == "Pre-seed":
        stage_terms = ["Pre-seed", "Seed"]
    else:
        # Unknown stage, cast wider
        stage_terms = ["Series A", "Series B", "Series C+"]

    stage_conditions = []
    params = []
    for st in stage_terms:
        stage_conditions.append("stage_preferred LIKE ?")
        params.append(f"%{st}%")

    # Geography: investor covers this country or is global
    geo_conditions = [
        "preferred_region LIKE ?",
        "preferred_region LIKE ?",
        "country = ?",
        "country = ?",
    ]
    params.extend([
        f"%{country}%",
        "%Any%",
        country,
        "CA" if country == "Canada" else country,
    ])

    sql = f"""
        SELECT * FROM investors
        WHERE ({" OR ".join(stage_conditions)})
          AND ({" OR ".join(geo_conditions)})
          AND investor_type NOT LIKE '%Broker%'
          AND investor_type NOT LIKE '%Pubco%'
          AND data_quality > 50
    """

    cursor = conn.execute(sql, params)
    results = rows_to_dicts(cursor.fetchall())
    print(f"  Pass 2 (Stage+Geo): {len(results)} investors for stage={stage_terms}, geo={country}")
    return results


# ---------------------------------------------------------------------------
# Pass 3: Adjacent Sector Match
# ---------------------------------------------------------------------------

def pass3_adjacent_sector(conn: sqlite3.Connection, company: dict) -> list[dict]:
    """Query investors in adjacent sectors that overlap with the company's space."""
    sector = company.get("company", {}).get("sector", "Other")
    adjacent = ADJACENT_SECTORS.get(sector, ["Climate / Cleantech General"])

    # Exclude terms already used in Pass 1
    direct_terms = set(SECTOR_TO_DB_TERMS.get(sector, []))
    adjacent_only = [t for t in adjacent if t not in direct_terms]

    if not adjacent_only:
        print(f"  Pass 3 (Adjacent): 0 investors (no unique adjacent terms)")
        return []

    conditions = []
    params = []
    for term in adjacent_only:
        conditions.append("industry_preferred LIKE ?")
        params.append(f"%{term}%")

    sql = f"""
        SELECT * FROM investors
        WHERE ({" OR ".join(conditions)})
          AND investor_type NOT LIKE '%Broker%'
          AND investor_type NOT LIKE '%Pubco%'
    """

    cursor = conn.execute(sql, params)
    results = rows_to_dicts(cursor.fetchall())
    print(f"  Pass 3 (Adjacent Sector): {len(results)} investors for terms {adjacent_only}")
    return results


# ---------------------------------------------------------------------------
# Pass 4: Impact Thesis Match
# ---------------------------------------------------------------------------

def pass4_impact_thesis(conn: sqlite3.Connection, company: dict) -> list[dict]:
    """Impact/sustainability investors who organize by outcome, not sector."""
    sql = """
        SELECT * FROM investors
        WHERE (
            investor_type LIKE '%Impact%'
            OR investor_type LIKE '%Sustainability%'
            OR industry_preferred LIKE '%Climate%'
            OR industry_preferred LIKE '%Cleantech%'
        )
        AND investor_type NOT LIKE '%Broker%'
        AND investor_type NOT LIKE '%Pubco%'
    """

    cursor = conn.execute(sql)
    results = rows_to_dicts(cursor.fetchall())
    print(f"  Pass 4 (Impact Thesis): {len(results)} investors")
    return results


# ---------------------------------------------------------------------------
# Pass 5: Relationship-First Match
# ---------------------------------------------------------------------------

def pass5_relationship_first(conn: sqlite3.Connection, company: dict) -> list[dict]:
    """Strongest ClimateDoor relationships regardless of sector fit."""
    sql = """
        SELECT * FROM investors
        WHERE warmth IN ('Hot', 'Warm', 'Personal', 'Met in person', 'Already Invested')
          AND investor_type NOT LIKE '%Broker%'
          AND investor_type NOT LIKE '%Pubco%'
        ORDER BY data_quality DESC
        LIMIT 60
    """

    cursor = conn.execute(sql)
    results = rows_to_dicts(cursor.fetchall())
    print(f"  Pass 5 (Relationship-First): {len(results)} investors with warm+ relationships")
    return results


# ---------------------------------------------------------------------------
# Multi-pass merge + de-duplication
# ---------------------------------------------------------------------------

def merge_passes(passes: dict[str, list[dict]]) -> dict[str, dict]:
    """Merge all passes, track which passes found each investor, compute multi-dim bonus."""
    all_matches = {}

    for pass_name, results in passes.items():
        for inv in results:
            inv_id = inv["id"]
            if inv_id not in all_matches:
                all_matches[inv_id] = {
                    "investor": inv,
                    "found_in_passes": [pass_name],
                    "pass_count": 1,
                }
            else:
                all_matches[inv_id]["found_in_passes"].append(pass_name)
                all_matches[inv_id]["pass_count"] += 1

    # Multi-dimensional match bonus: +5 per pass, max +15
    for match in all_matches.values():
        match["multi_dim_bonus"] = min(match["pass_count"] * 5, 15)

    return all_matches


# ---------------------------------------------------------------------------
# 6-Factor Weighted Scoring (deterministic, from DB fields only)
# ---------------------------------------------------------------------------

def score_thesis_fit(inv: dict, company: dict) -> int:
    """Factor 1: How well does industry_preferred align with company sector?"""
    sector = company.get("company", {}).get("sector", "")
    sub_sector = company.get("company", {}).get("sub_sector", "")
    industry = (inv.get("industry_preferred") or "").lower()

    if not industry:
        return 20  # No data, low but not zero (found via some pass)

    direct_terms = SECTOR_TO_DB_TERMS.get(sector, [])
    adjacent_terms = ADJACENT_SECTORS.get(sector, [])

    # Count how many direct terms match
    direct_hits = sum(1 for t in direct_terms if t.lower() in industry)
    adjacent_hits = sum(1 for t in adjacent_terms if t.lower() in industry)

    # Check for broad climate/cleantech match
    climate_general = "climate" in industry or "cleantech" in industry

    if direct_hits >= 2:
        return 90  # Strong multi-term direct match
    elif direct_hits == 1 and adjacent_hits >= 1:
        return 82  # Direct + adjacent
    elif direct_hits == 1:
        return 75  # Single direct match
    elif climate_general and adjacent_hits >= 1:
        return 65  # Climate generalist with adjacent interest
    elif adjacent_hits >= 2:
        return 62  # Multiple adjacent matches
    elif adjacent_hits == 1:
        return 50  # Single adjacent match
    elif climate_general:
        return 45  # Climate generalist only
    elif inv.get("climate_investments", 0) and inv["climate_investments"] > 0:
        return 40  # Has made climate investments but no matching tags
    else:
        return 20  # No visible alignment


def score_stage_fit(inv: dict, company: dict) -> int:
    """Factor 2: Does investor's stage preference match company's stage?"""
    company_stage = company.get("company", {}).get("stage", "")
    inv_stages = (inv.get("stage_preferred") or "").lower()

    if not inv_stages:
        return 50  # No stage data, neutral

    if not company_stage:
        return 50

    # Map company stage to what we look for in investor preferences
    stage_map = {
        "Pre-seed": ["pre-seed"],
        "Seed": ["seed", "pre-seed"],
        "Series A": ["series a"],
        "Series B": ["series b"],
        "Series C+": ["series c"],
        "Growth": ["series b", "series c", "mezzanine"],
        "Bridge": ["series b", "series c", "mezzanine"],
        "IPO": ["series c", "mezzanine"],
        "PubCo": ["series c"],
    }

    target_terms = stage_map.get(company_stage, ["series a", "series b"])

    # Check for exact match, adjacent match, or mismatch
    exact_hits = sum(1 for t in target_terms if t in inv_stages)
    any_overlap = exact_hits > 0

    if exact_hits >= 2:
        return 90  # Sweet spot
    elif exact_hits == 1:
        return 78  # Within range
    else:
        # Check if adjacent (one stage away)
        all_stages = ["pre-seed", "seed", "series a", "series b", "series c", "mezzanine"]
        inv_stage_indices = [i for i, s in enumerate(all_stages) if s in inv_stages]
        target_indices = [i for i, s in enumerate(all_stages) if s in " ".join(target_terms)]
        if inv_stage_indices and target_indices:
            min_gap = min(abs(ii - ti) for ii in inv_stage_indices for ti in target_indices)
            if min_gap == 1:
                return 55  # Adjacent stage
            elif min_gap == 2:
                return 35  # Two stages away
        return 20  # Clear mismatch


def score_geo_fit(inv: dict, company: dict) -> int:
    """Factor 3: Geography alignment."""
    geo = company.get("company", {}).get("geography", {})
    hq = geo.get("hq", "")

    inv_region = (inv.get("preferred_region") or "").lower()
    inv_country = (inv.get("country") or "").lower()
    inv_city = (inv.get("city") or "").lower()
    inv_state = (inv.get("state") or "").lower()

    # Determine company location
    company_country = "canada" if ("canada" in hq.lower() or "quebec" in hq.lower()) else ""
    company_province = "quebec" if "quebec" in hq.lower() else ""

    if not inv_region and not inv_country:
        return 50  # No data, neutral

    # Check for same-province/city match
    if company_province and (company_province in inv_state.lower() or company_province in inv_city.lower()):
        return 95  # Same province

    # Check preferred_region or country for Canada
    if "any" in inv_region or "all" in inv_region:
        return 65  # Global, no restrictions

    if company_country:
        if company_country in inv_region or inv_country in ("canada", "ca"):
            return 82  # Explicitly covers Canada
        elif "usa" in inv_region or "united states" in inv_country:
            return 60  # North American, adjacent
        elif inv_region:
            return 30  # Has preferences that don't include Canada

    return 50  # Uncertain


def score_intro_warmth(inv: dict) -> int:
    """Factor 4: Intro path warmth from DB."""
    warmth = inv.get("warmth") or ""
    return WARMTH_SCORES.get(warmth, 15)


def score_fund_activity(inv: dict) -> int:
    """Factor 5: Fund activity indicators from DB fields."""
    # We don't have last_active date, so use proxies:
    # - data_quality as a signal (higher = more recently updated/verified)
    # - climate_investments count
    # - VIP flag
    dq = inv.get("data_quality") or 0
    climate_inv = inv.get("climate_investments") or 0
    vip = inv.get("vip") or 0

    score = 30  # baseline

    if dq >= 90:
        score += 25
    elif dq >= 75:
        score += 15
    elif dq >= 50:
        score += 5

    if climate_inv >= 21:
        score += 25  # Very active
    elif climate_inv >= 6:
        score += 15
    elif climate_inv >= 1:
        score += 10

    if vip:
        score += 10

    return min(score, 100)


def score_portfolio_signal(inv: dict, company: dict) -> int:
    """Factor 6: Portfolio signal. Without external data, use heuristics."""
    # For now, score based on investor type and whether they have a broad portfolio
    inv_type = (inv.get("investor_type") or "").lower()
    climate_inv = inv.get("climate_investments") or 0
    industry = (inv.get("industry_preferred") or "").lower()

    sector = company.get("company", {}).get("sector", "").lower()

    if climate_inv >= 21:
        # Active portfolio, likely some overlap
        if any(t.lower() in industry for t in SECTOR_TO_DB_TERMS.get(company.get("company", {}).get("sector", "Other"), [])):
            return 75  # Active in the sector
        return 55  # Active but different sectors
    elif climate_inv >= 1:
        return 50  # Some portfolio, no conflicts known
    else:
        return 45  # No portfolio data, neutral


def compute_total_score(inv: dict, company: dict, multi_dim_bonus: int) -> dict:
    """Compute the full 6-factor weighted score plus multi-dim bonus."""
    thesis = score_thesis_fit(inv, company)
    stage = score_stage_fit(inv, company)
    geo = score_geo_fit(inv, company)
    warmth = score_intro_warmth(inv)
    activity = score_fund_activity(inv)
    portfolio = score_portfolio_signal(inv, company)

    # Weighted formula from investor-scoring.md
    total = (
        thesis * 0.25
        + stage * 0.20
        + geo * 0.10
        + warmth * 0.25
        + activity * 0.10
        + portfolio * 0.10
        + multi_dim_bonus
    )

    return {
        "total_score": round(total, 1),
        "breakdown": {
            "thesis_fit": thesis,
            "stage_fit": stage,
            "geo_fit": geo,
            "intro_warmth": warmth,
            "fund_activity": activity,
            "portfolio_signal": portfolio,
            "multi_dim_bonus": multi_dim_bonus,
        },
    }


# ---------------------------------------------------------------------------
# Action level classification
# ---------------------------------------------------------------------------

def classify_action_level(score: float) -> str:
    if score >= 85:
        return "act_now"
    elif score >= 70:
        return "know"
    elif score >= 55:
        return "watch"
    else:
        return "exclude"


# ---------------------------------------------------------------------------
# Sonnet scoring + web verification for top candidates
# ---------------------------------------------------------------------------

SONNET_SCORING_SYSTEM = """You are an investor matching analyst for ClimateDoor, a climate venture advisory firm.

You are evaluating a shortlist of pre-scored investor matches for a specific company. Your job is to:

1. Evaluate each candidate's fit based on the company profile and the investor's DB record
2. Generate a 2-3 sentence thesis summary explaining WHY this investor would be interested
3. Generate a 2-3 sentence approach recommendation for how to position the pitch
4. Generate 2-3 insight bullet points connecting this investor to the company's situation
5. Assess confidence in the match

CRITICAL RULES:
- Every investor name MUST come from the database. You must NOT fabricate investor names.
- The fund name (organization) must come from the DB record.
- Intro warmth comes from the DB warmth field. Do NOT invent warm relationships.
- If warmth is empty or "Cold", the intro type is "cold" - do NOT upgrade it.
- Be honest about data gaps. If you don't know the fund's current deployment status, say so.
- Do NOT fabricate portfolio companies, deal sizes, or recent activity.

For each investor, output a JSON object with these fields:
- thesis_summary: 2-3 sentences on why this fund would be interested (based on their industry tags and type)
- approach: 2-3 sentences on positioning strategy
- insights: array of 2-3 bullet points
- intro_path: {type: warm|network|cold, detail: string, source: string}
- confidence_notes: what data supports this match and what gaps remain

Output a JSON array of objects, one per investor."""


def build_company_summary(company: dict) -> dict:
    """Build a compact company summary for Sonnet prompts."""
    comp = company.get("company", {})
    product = company.get("product", {})
    traction = company.get("traction", {})
    return {
        "name": comp.get("name", ""),
        "sector": comp.get("sector", ""),
        "sub_sector": comp.get("sub_sector", ""),
        "stage": comp.get("stage", ""),
        "trl": comp.get("trl", ""),
        "geography": comp.get("geography", {}),
        "description": comp.get("description", ""),
        "product_description": product.get("description", ""),
        "key_claims": [c.get("claim", "") for c in product.get("key_claims", [])[:5]],
        "regulatory": {
            k: v.get("status", "") for k, v in product.get("regulatory_status", {}).items()
        },
        "patents": [p.get("title", "") for p in product.get("ip", {}).get("patents", [])],
        "government_traction": traction.get("government_buyer_traction", False),
        "logos": [l.get("name", "") for l in traction.get("website_logos", [])],
        "target_buyers": company.get("market", {}).get("target_buyers", []),
        "data_gaps": company.get("data_gaps", [])[:5],
        "funding": company.get("funding", {}),
    }


def build_candidate_summary(c: dict) -> dict:
    """Build a compact candidate summary for Sonnet prompts."""
    inv = c["investor"]
    score = c["score"]
    return {
        "db_id": inv["id"],
        "name": inv["full_name"],
        "organization": inv["organization"] or "Independent",
        "investor_type": inv["investor_type"] or "Unknown",
        "industry_preferred": inv["industry_preferred"] or "Not specified",
        "stage_preferred": inv["stage_preferred"] or "Not specified",
        "cheque_size": inv["cheque_size"] or "Not specified",
        "preferred_region": inv["preferred_region"] or "Not specified",
        "warmth": inv["warmth"] or "Cold/Unknown",
        "climate_investments": inv["climate_investments"] or 0,
        "is_lead_investor": bool(inv["is_lead_investor"]),
        "vip": bool(inv["vip"]),
        "hw_sw": inv["hw_sw"] or "Not specified",
        "data_quality": inv["data_quality"] or 0,
        "notes": (inv.get("notes") or "")[:300],
        "more_info": (inv.get("more_info") or "")[:300],
        "country": inv["country"] or "",
        "city": inv["city"] or "",
        "total_score": score["total_score"],
        "score_breakdown": score["breakdown"],
        "found_in_passes": c["found_in_passes"],
    }


def call_sonnet_batch(client: anthropic.Anthropic, batch: list[dict],
                      company_summary: dict, batch_num: int) -> list[dict]:
    """Call Sonnet for a single batch of candidates. Returns parsed eval list."""
    user_msg = f"""Evaluate these {len(batch)} investor candidates for this company.

COMPANY PROFILE:
{json.dumps(company_summary, indent=2)}

INVESTOR CANDIDATES (pre-scored, sorted by total_score descending):
{json.dumps(batch, indent=2)}

For each investor, provide your analysis. Output ONLY a JSON array of objects with these fields per investor:
- db_id: the investor's id from the DB (MUST match the input exactly)
- thesis_summary: 2-3 sentences on why this fund would be interested
- approach: 2-3 sentences on how to position the pitch
- insights: array of 2-3 bullet point strings
- intro_path: {{type: "warm"|"network"|"cold", detail: string, source: "database_warmth_field"}}
- confidence_notes: 1-2 sentences on data quality

IMPORTANT: Base intro_path.type strictly on the warmth field:
- "Hot", "Personal", "Met in person", "Already Invested" -> type: "warm"
- "Warm", "Connected Online" -> type: "network"
- Everything else ("Cold", "Target", empty) -> type: "cold"

Be concise. Output ONLY the JSON array."""

    print(f"    Batch {batch_num}: {len(batch)} candidates...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=16000,
        system=SONNET_SCORING_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    elapsed = time.time() - t0

    raw = response.content[0].text.strip()
    print(f"    Batch {batch_num} done in {elapsed:.1f}s "
          f"({response.usage.input_tokens} in / {response.usage.output_tokens} out)")

    # Parse JSON
    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        print(f"    [WARN] Batch {batch_num} JSON parse failed, using fallback")
        return []


def run_sonnet_evaluation(candidates: list[dict], company: dict) -> dict:
    """Send top candidates to Sonnet in batches for thesis analysis."""
    client = anthropic.Anthropic()
    company_summary = build_company_summary(company)

    # Build summaries
    candidate_summaries = [build_candidate_summary(c) for c in candidates]

    # Split into batches of 10 to stay within output token limits
    BATCH_SIZE = 10
    batches = [candidate_summaries[i:i+BATCH_SIZE]
               for i in range(0, len(candidate_summaries), BATCH_SIZE)]

    print(f"\n  Calling Sonnet in {len(batches)} batch(es) of up to {BATCH_SIZE}...")

    all_evals = []
    for i, batch in enumerate(batches, 1):
        evals = call_sonnet_batch(client, batch, company_summary, i)
        all_evals.extend(evals)

    # Index by db_id
    eval_map = {}
    for ev in all_evals:
        eval_map[str(ev.get("db_id", ""))] = ev

    print(f"  Sonnet evaluated {len(eval_map)} / {len(candidates)} candidates successfully")
    return eval_map


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_step2(slug: str) -> Path:
    """Run the full 5-pass investor matching pipeline."""
    data_dir = SKILL_ROOT / "data" / slug
    step1_path = data_dir / "step1-company.json"
    output_path = data_dir / "step2-investors.json"

    if not step1_path.exists():
        print(f"ERROR: {step1_path} not found. Run Step 1 first.")
        sys.exit(1)

    with open(step1_path) as f:
        company = json.load(f)

    comp = company.get("company", {})
    print(f"=" * 60)
    print(f"STEP 2: Multi-Pass Investor Matching")
    print(f"Company: {comp.get('name', 'Unknown')}")
    print(f"Sector:  {comp.get('sector', 'Unknown')}")
    print(f"Stage:   {comp.get('stage', 'Unknown')}")
    print(f"HQ:      {comp.get('geography', {}).get('hq', 'Unknown')}")
    print(f"DB:      {INVESTOR_DB} (2,645 records)")
    print(f"Output:  {output_path}")
    print(f"=" * 60)

    # --- Phase 1: 5-pass queries ---
    print(f"\n[Phase 1] Running 5 query passes against investor DB...")
    conn = get_db_connection()

    passes = {
        "pass1_direct_sector": pass1_direct_sector(conn, company),
        "pass2_stage_geography": pass2_stage_geography(conn, company),
        "pass3_adjacent_sector": pass3_adjacent_sector(conn, company),
        "pass4_impact_thesis": pass4_impact_thesis(conn, company),
        "pass5_relationship_first": pass5_relationship_first(conn, company),
    }
    conn.close()

    # Log pass counts
    total_raw = sum(len(v) for v in passes.values())
    print(f"\n  Total raw hits across all passes: {total_raw}")

    # --- Phase 2: Merge + de-duplicate ---
    print(f"\n[Phase 2] Merging and de-duplicating...")
    merged = merge_passes(passes)
    print(f"  Unique investors after merge: {len(merged)}")

    # Log multi-pass overlaps
    multi_pass = [m for m in merged.values() if m["pass_count"] >= 2]
    three_plus = [m for m in merged.values() if m["pass_count"] >= 3]
    print(f"  Found in 2+ passes: {len(multi_pass)}")
    print(f"  Found in 3+ passes: {len(three_plus)}")

    # --- Phase 3: Deterministic scoring ---
    print(f"\n[Phase 3] Computing 6-factor weighted scores...")
    scored = []
    for inv_id, match in merged.items():
        inv = match["investor"]
        score = compute_total_score(inv, company, match["multi_dim_bonus"])
        scored.append({
            "investor": inv,
            "score": score,
            "found_in_passes": match["found_in_passes"],
            "pass_count": match["pass_count"],
        })

    # Sort by total score descending
    scored.sort(key=lambda x: x["score"]["total_score"], reverse=True)

    # Log score distribution
    scores = [s["score"]["total_score"] for s in scored]
    if scores:
        print(f"  Score range: {min(scores):.1f} - {max(scores):.1f}")
        print(f"  Median: {scores[len(scores)//2]:.1f}")
        above_55 = sum(1 for s in scores if s >= 55)
        above_70 = sum(1 for s in scores if s >= 70)
        above_85 = sum(1 for s in scores if s >= 85)
        print(f"  WATCH (55+): {above_55}, KNOW (70+): {above_70}, ACT NOW (85+): {above_85}")

    # --- Phase 4: Take top 20 for Sonnet evaluation ---
    top_n = min(20, len(scored))
    top_candidates = scored[:top_n]
    print(f"\n[Phase 4] Sending top {top_n} to Sonnet for evaluation...")

    for i, c in enumerate(top_candidates[:5]):
        inv = c["investor"]
        s = c["score"]
        print(f"  #{i+1}: {inv['full_name']} @ {inv['organization'] or 'Independent'} "
              f"| Score: {s['total_score']:.1f} | Passes: {c['found_in_passes']}")

    eval_map = run_sonnet_evaluation(top_candidates, company)

    # --- Phase 5: Assemble final output ---
    print(f"\n[Phase 5] Assembling final investor list...")
    final_investors = []
    for c in top_candidates:
        inv = c["investor"]
        s = c["score"]
        action = classify_action_level(s["total_score"])

        if action == "exclude":
            continue

        ev = eval_map.get(str(inv["id"]), {})

        entry = {
            "name": inv["full_name"],
            "fund": inv["organization"] or "Independent",
            "db_id": inv["id"],
            "score": s["total_score"],
            "score_breakdown": s["breakdown"],
            "action_level": action,
            "check_size": inv["cheque_size"] or "Not specified",
            "investor_type": inv["investor_type"] or "Unknown",
            "stage_preferred": inv["stage_preferred"] or "Not specified",
            "industry_preferred": inv["industry_preferred"] or "Not specified",
            "preferred_region": inv["preferred_region"] or "Not specified",
            "country": inv["country"] or "",
            "thesis_summary": ev.get("thesis_summary", "Evaluation pending - requires web verification"),
            "intro_path": ev.get("intro_path", {
                "type": "cold" if not inv.get("warmth") or inv["warmth"] in ("", "Cold", "Target") else "warm",
                "detail": f"DB warmth: {inv.get('warmth', 'unknown')}",
                "source": "database",
            }),
            "approach": ev.get("approach", ""),
            "insights": ev.get("insights", []),
            "confidence_notes": ev.get("confidence_notes", ""),
            "found_in_passes": c["found_in_passes"],
            "pass_count": c["pass_count"],
            "verified": False,  # Not yet web-verified
        }
        final_investors.append(entry)

    # --- Phase 6: Build output JSON ---
    output = {
        "company": comp.get("name", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": SONNET_MODEL,
        "pipeline_stats": {
            "db_total_records": 2645,
            "pass1_direct_sector": len(passes["pass1_direct_sector"]),
            "pass2_stage_geography": len(passes["pass2_stage_geography"]),
            "pass3_adjacent_sector": len(passes["pass3_adjacent_sector"]),
            "pass4_impact_thesis": len(passes["pass4_impact_thesis"]),
            "pass5_relationship_first": len(passes["pass5_relationship_first"]),
            "total_raw_hits": total_raw,
            "unique_after_merge": len(merged),
            "found_in_2_plus_passes": len(multi_pass),
            "found_in_3_plus_passes": len(three_plus),
            "candidates_scored": len(scored),
            "candidates_sent_to_sonnet": top_n,
            "final_matches": len(final_investors),
        },
        "action_summary": {
            "act_now": sum(1 for i in final_investors if i["action_level"] == "act_now"),
            "know": sum(1 for i in final_investors if i["action_level"] == "know"),
            "watch": sum(1 for i in final_investors if i["action_level"] == "watch"),
        },
        "investors": final_investors,
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"STEP 2 COMPLETE")
    print(f"  Output: {output_path}")
    print(f"  Total matches: {len(final_investors)}")
    print(f"  ACT NOW: {output['action_summary']['act_now']}")
    print(f"  KNOW:    {output['action_summary']['know']}")
    print(f"  WATCH:   {output['action_summary']['watch']}")
    if final_investors:
        print(f"  Top match: {final_investors[0]['name']} @ {final_investors[0]['fund']} ({final_investors[0]['score']})")
    print(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step2_investor_matching.py <company-slug>")
        print("Example: python3 step2_investor_matching.py frett-design")
        sys.exit(1)

    slug = sys.argv[1]
    output = run_step2(slug)
    print(f"\nDone. Output at: {output}")
