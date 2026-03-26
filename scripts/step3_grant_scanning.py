#!/usr/bin/env python3
"""
Step 3: Grant Scanning (Self-Contained)
Model: Sonnet with web search tool
Input: data/[slug]/step1-company.json
Output: data/[slug]/step3-grants.json

Self-contained grant discovery:
  1. Read company profile from step1-company.json
  2. Query Notion grant database with proper field-level filtering
  3. Web search for matching grant programs via Anthropic API
  4. Score all grants against company using Sonnet
  5. Grants-as-BD analysis (grants the company's CUSTOMERS can get)
  6. Optionally add new web-discovered grants to Notion
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
import requests as req_lib

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")

# Notion config
NOTION_TOKEN = os.environ.get("NOTION_API_TOKEN", "")
NOTION_GRANT_DB = os.environ.get("NOTION_GRANT_DB", "1ac588f311298024b65accdfe6377bb1")
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Sector-to-Notion-Category mapping
# ---------------------------------------------------------------------------
# Maps ICP / step1 sectors to the Notion "Categories" multi_select values
SECTOR_TO_CATEGORIES = {
    # Cleantech / Energy
    "cleantech": ["Clean Energy / Environment"],
    "clean technology": ["Clean Energy / Environment"],
    "clean energy": ["Clean Energy / Environment"],
    "renewable energy": ["Clean Energy / Environment"],
    "energy": ["Clean Energy / Environment"],
    "solar": ["Clean Energy / Environment"],
    "wind": ["Clean Energy / Environment"],
    "battery": ["Clean Energy / Environment", "Technology"],
    "hydrogen": ["Clean Energy / Environment"],
    "carbon capture": ["Clean Energy / Environment"],
    "environment": ["Clean Energy / Environment"],
    "sustainability": ["Clean Energy / Environment"],
    "waste management": ["Clean Energy / Environment"],
    "water": ["Clean Energy / Environment"],
    "circular economy": ["Clean Energy / Environment"],

    # Tech
    "technology": ["Technology"],
    "software": ["Technology"],
    "saas": ["Technology"],
    "ai": ["Technology"],
    "artificial intelligence": ["Technology"],
    "machine learning": ["Technology"],
    "iot": ["Technology"],
    "fintech": ["Technology"],
    "cybersecurity": ["Technology"],
    "blockchain": ["Technology"],
    "robotics": ["Technology"],

    # Health
    "health": ["Health"],
    "healthcare": ["Health"],
    "medtech": ["Health"],
    "biotech": ["Health"],
    "life sciences": ["Health"],
    "pharma": ["Health"],
    "medical devices": ["Health"],

    # Agriculture
    "agriculture": ["Agriculture"],
    "agtech": ["Agriculture"],
    "agritech": ["Agriculture"],
    "food": ["Agriculture"],
    "foodtech": ["Agriculture"],
    "aquaculture": ["Agriculture"],

    # Economic Development
    "economic development": ["Economic Development"],
    "manufacturing": ["Economic Development"],
    "industrial": ["Economic Development"],
    "mining": ["Economic Development"],
    "forestry": ["Economic Development"],
    "natural resources": ["Economic Development"],

    # Housing and Infrastructure
    "construction": ["Housing and Infrastructure"],
    "housing": ["Housing and Infrastructure"],
    "infrastructure": ["Housing and Infrastructure"],
    "real estate": ["Housing and Infrastructure"],
    "building": ["Housing and Infrastructure"],

    # Entrepreneurship
    "entrepreneurship": ["Entrepreneurship"],
    "startup": ["Entrepreneurship"],
    "small business": ["Entrepreneurship"],
}


def map_sector_to_categories(sector: str, sub_sector: str = "") -> list[str]:
    """Map a company's sector (and sub_sector) to Notion Categories values."""
    categories = set()

    for text in [sector.lower(), sub_sector.lower()]:
        if not text:
            continue
        # Direct match
        if text in SECTOR_TO_CATEGORIES:
            categories.update(SECTOR_TO_CATEGORIES[text])
        else:
            # Partial match - check if any key is contained in the text
            for key, vals in SECTOR_TO_CATEGORIES.items():
                if key in text or text in key:
                    categories.update(vals)

    # Default: if nothing matched, return broad categories
    if not categories:
        categories = {"Economic Development", "Technology"}

    return list(categories)


def map_geography_to_regions(geography: dict) -> list[str]:
    """Map a company's geography to Notion Region values."""
    regions = set()
    hq = geography.get("hq", "")

    # Always include Canada
    regions.add("Canada")

    # Province mapping
    province_map = {
        "british columbia": "BC",
        "bc": "BC",
        "ontario": "Ontario",
        "on": "Ontario",
        "alberta": "Alberta",
        "ab": "Alberta",
        "quebec": "Quebec",
        "qc": "Quebec",
        "manitoba": "Manitoba",
        "mb": "Manitoba",
        "saskatchewan": "Saskatchewan",
        "sk": "Saskatchewan",
        "nova scotia": "Nova Scotia",
        "ns": "Nova Scotia",
        "new brunswick": "New Brunswick",
        "nb": "New Brunswick",
        "newfoundland": "Newfoundland",
        "nl": "Newfoundland",
        "prince edward island": "PEI",
        "pei": "PEI",
        "northwest territories": "Northwest Territories",
        "nt": "Northwest Territories",
        "nunavut": "Nunavut",
        "nu": "Nunavut",
        "yukon": "Yukon",
        "yt": "Yukon",
    }

    hq_lower = hq.lower()
    for key, region in province_map.items():
        if key in hq_lower:
            regions.add(region)
            # Check for sub-regions
            if region == "BC":
                # Check for Northern BC indicators
                northern_bc_cities = [
                    "prince george", "terrace", "kitimat", "fort st john",
                    "dawson creek", "prince rupert", "smithers", "quesnel",
                    "williams lake", "vanderhoof", "burns lake",
                ]
                for city in northern_bc_cities:
                    if city in hq_lower:
                        regions.add("Northern BC")
                        break

    return list(regions)


# ---------------------------------------------------------------------------
# Notion helpers
# ---------------------------------------------------------------------------

def build_notion_filter(categories: list[str], regions: list[str]) -> dict:
    """
    Build a Notion compound filter that:
      - Categories matches any of the mapped categories
      - Eligible Groups contains "For-Profit"
      - Intake - NEW is NOT "Closed" and NOT "Ended Permanently"
    """
    # Category conditions: OR across categories (any match)
    category_conditions = []
    for cat in categories:
        category_conditions.append({
            "property": "Categories",
            "multi_select": {
                "contains": cat,
            },
        })

    # Region conditions: OR across regions
    region_conditions = []
    for region in regions:
        region_conditions.append({
            "property": "Region",
            "multi_select": {
                "contains": region,
            },
        })

    # Eligible Groups must contain "For-Profit"
    eligible_condition = {
        "property": "Eligible Groups",
        "multi_select": {
            "contains": "For-Profit",
        },
    }

    # Intake - NEW must NOT be "Closed", "Ended Permanently", or "Closed Until Further Notice"
    intake_not_closed = {
        "property": "Intake - NEW",
        "multi_select": {
            "does_not_contain": "Closed",
        },
    }
    intake_not_ended = {
        "property": "Intake - NEW",
        "multi_select": {
            "does_not_contain": "Ended Permanently",
        },
    }
    intake_not_closed_further = {
        "property": "Intake - NEW",
        "multi_select": {
            "does_not_contain": "Closed Until Further Notice",
        },
    }

    # Build the compound filter
    # Logic: (any category matches) AND (any region matches) AND (For-Profit) AND (not closed) AND (not ended) AND (not closed until further notice)
    filter_obj = {
        "and": [
            # At least one category must match
            {"or": category_conditions} if len(category_conditions) > 1 else category_conditions[0],
            # At least one region must match
            {"or": region_conditions} if len(region_conditions) > 1 else region_conditions[0],
            # Must be eligible for For-Profit
            eligible_condition,
            # Must not be closed or ended
            intake_not_closed,
            intake_not_ended,
            intake_not_closed_further,
        ],
    }

    return filter_obj


def extract_notion_grant(page: dict) -> dict:
    """Extract a structured grant record from a Notion page."""
    props = page.get("properties", {})

    # Extract title from "Grant Name"
    title = ""
    grant_name_prop = props.get("Grant Name", {})
    for t in grant_name_prop.get("title", []):
        title += t.get("plain_text", "")

    # Extract multi_select fields
    def get_multi_select(prop_name: str) -> list[str]:
        prop = props.get(prop_name, {})
        if prop.get("type") == "multi_select":
            return [o.get("name", "") for o in prop.get("multi_select", [])]
        return []

    categories = get_multi_select("Categories")
    eligible_groups = get_multi_select("Eligible Groups")
    regions = get_multi_select("Region")
    intake_status = get_multi_select("Intake - NEW")
    funding_type = get_multi_select("Funding Type")
    type_of_funding = get_multi_select("Type of Funding")

    # Extract URL
    website = ""
    website_prop = props.get("Website", {})
    if website_prop.get("type") == "url":
        website = website_prop.get("url", "") or ""

    # Extract dates
    def get_date(prop_name: str) -> str | None:
        prop = props.get(prop_name, {})
        if prop.get("type") == "date":
            date_obj = prop.get("date") or {}
            return date_obj.get("start")
        return None

    app_start = get_date("Application Start Date")
    app_end = get_date("Application End Date")

    # Also extract any rich_text or number fields that might be present
    extra_fields = {}
    skip_keys = {
        "Grant Name", "Categories", "Eligible Groups", "Region",
        "Intake - NEW", "Funding Type", "Type of Funding", "Website",
        "Application Start Date", "Application End Date",
    }
    for key, prop in props.items():
        if key in skip_keys:
            continue
        ptype = prop.get("type", "")
        if ptype == "rich_text":
            text = "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
            if text:
                extra_fields[key.lower().replace(" ", "_")] = text
        elif ptype == "number":
            val = prop.get("number")
            if val is not None:
                extra_fields[key.lower().replace(" ", "_")] = val
        elif ptype == "select":
            val = (prop.get("select") or {}).get("name", "")
            if val:
                extra_fields[key.lower().replace(" ", "_")] = val
        elif ptype == "multi_select":
            vals = [o.get("name", "") for o in prop.get("multi_select", [])]
            if vals:
                extra_fields[key.lower().replace(" ", "_")] = vals
        elif ptype == "url":
            val = prop.get("url", "")
            if val:
                extra_fields[key.lower().replace(" ", "_")] = val
        elif ptype == "date":
            date_obj = prop.get("date") or {}
            if date_obj.get("start"):
                extra_fields[key.lower().replace(" ", "_")] = date_obj["start"]

    grant = {
        "program_name": title,
        "source": "notion_db",
        "notion_page_id": page["id"],
        "notion_page_url": page.get("url", ""),
        "categories": categories,
        "eligible_groups": eligible_groups,
        "region": regions,
        "intake_status": intake_status,
        "funding_type": funding_type,
        "type_of_funding": type_of_funding,
        "website": website,
        "application_start_date": app_start,
        "application_end_date": app_end,
    }

    # Merge any extra fields
    grant.update(extra_fields)

    return grant


def query_notion_grants(sector: str, sub_sector: str, geography: dict) -> list[dict]:
    """Query Notion grant database with proper field-level filtering.

    Filters by:
      - Categories matching mapped sector categories
      - Eligible Groups containing "For-Profit"
      - Intake - NEW NOT containing "Closed" or "Ended Permanently"
      - Region matching the company's geography

    Returns list of grant dicts, or empty list on failure.
    """
    if not NOTION_TOKEN:
        print("  [SKIP] No NOTION_API_TOKEN configured")
        return []

    categories = map_sector_to_categories(sector, sub_sector)
    regions = map_geography_to_regions(geography)

    print(f"  Mapped sector '{sector}' / '{sub_sector}' -> Categories: {categories}")
    print(f"  Mapped geography -> Regions: {regions}")

    try:
        # Build the filter
        notion_filter = build_notion_filter(categories, regions)
        print(f"  Querying Notion with filter...")

        all_grants = []
        has_more = True
        start_cursor = None
        page_num = 0

        while has_more:
            page_num += 1
            body = {
                "page_size": 100,
                "filter": notion_filter,
            }
            if start_cursor:
                body["start_cursor"] = start_cursor

            r = req_lib.post(
                f"https://api.notion.com/v1/databases/{NOTION_GRANT_DB}/query",
                headers=NOTION_HEADERS,
                json=body,
                timeout=15,
            )

            if r.status_code == 404:
                print(f"  [SKIP] Notion grant DB not accessible (not shared with integration)")
                return []

            if r.status_code == 400:
                # Filter might be invalid - try a simpler filter
                print(f"  [WARN] Notion filter rejected ({r.status_code}): {r.text[:300]}")
                print(f"  Falling back to simpler query...")
                return _query_notion_grants_simple(categories)

            if r.status_code != 200:
                print(f"  [WARN] Notion query failed ({r.status_code}): {r.text[:200]}")
                return []

            data = r.json()
            results = data.get("results", [])
            print(f"  Page {page_num}: got {len(results)} results")

            for page in results:
                grant = extract_notion_grant(page)
                if grant["program_name"]:  # Skip entries with no name
                    all_grants.append(grant)

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        print(f"  Found {len(all_grants)} matching grants in Notion DB (filtered)")
        return all_grants

    except Exception as e:
        print(f"  [WARN] Notion query failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def _query_notion_grants_simple(categories: list[str]) -> list[dict]:
    """Fallback: simpler Notion query with just category + for-profit filter."""
    try:
        # Just filter by one category and For-Profit
        simple_filter = {
            "and": [
                {
                    "property": "Categories",
                    "multi_select": {
                        "contains": categories[0],
                    },
                },
                {
                    "property": "Eligible Groups",
                    "multi_select": {
                        "contains": "For-Profit",
                    },
                },
            ],
        }

        r = req_lib.post(
            f"https://api.notion.com/v1/databases/{NOTION_GRANT_DB}/query",
            headers=NOTION_HEADERS,
            json={"page_size": 100, "filter": simple_filter},
            timeout=15,
        )

        if r.status_code != 200:
            print(f"  [WARN] Simple Notion query also failed ({r.status_code}): {r.text[:200]}")
            # Last resort: no filter
            return _query_notion_grants_unfiltered()

        results = r.json().get("results", [])
        grants = []
        for page in results:
            grant = extract_notion_grant(page)
            # Post-filter: skip closed/ended
            intake = grant.get("intake_status", [])
            if "Closed" in intake or "Ended Permanently" in intake or "Closed Until Further Notice" in intake:
                continue
            if grant["program_name"]:
                grants.append(grant)

        print(f"  Found {len(grants)} grants (simple filter, post-filtered)")
        return grants

    except Exception as e:
        print(f"  [WARN] Simple Notion query failed: {e}")
        return _query_notion_grants_unfiltered()


def _query_notion_grants_unfiltered() -> list[dict]:
    """Last-resort fallback: query with no filter, post-filter in Python."""
    try:
        print(f"  Trying unfiltered query (will post-filter in Python)...")

        all_grants = []
        has_more = True
        start_cursor = None

        while has_more:
            body = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor

            r = req_lib.post(
                f"https://api.notion.com/v1/databases/{NOTION_GRANT_DB}/query",
                headers=NOTION_HEADERS,
                json=body,
                timeout=15,
            )

            if r.status_code != 200:
                print(f"  [WARN] Unfiltered Notion query failed ({r.status_code})")
                return []

            data = r.json()
            results = data.get("results", [])

            for page in results:
                grant = extract_notion_grant(page)

                # Post-filter: skip closed/ended
                intake = grant.get("intake_status", [])
                if "Closed" in intake or "Ended Permanently" in intake or "Closed Until Further Notice" in intake:
                    continue

                # Post-filter: must include For-Profit
                eligible = grant.get("eligible_groups", [])
                if "For-Profit" not in eligible:
                    continue

                if grant["program_name"]:
                    all_grants.append(grant)

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        print(f"  Found {len(all_grants)} grants (unfiltered, post-filtered in Python)")
        return all_grants

    except Exception as e:
        print(f"  [WARN] Unfiltered Notion query failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Web search for grants
# ---------------------------------------------------------------------------

def search_grants_web(client: anthropic.Anthropic, company: dict) -> str:
    """Use Sonnet with web search to find grant programs matching the company."""
    comp = company.get("company", {})
    product = company.get("product", {})
    geo = comp.get("geography", {})

    hq = geo.get("hq", "Canada")
    province = ""
    if "," in hq:
        parts = [p.strip() for p in hq.split(",")]
        if len(parts) >= 2:
            province = parts[-2] if len(parts) >= 3 else parts[0]

    sector = comp.get("sector", "cleantech")
    sub_sector = comp.get("sub_sector", "")
    stage = comp.get("stage", "")
    trl = comp.get("trl", "")
    product_desc = product.get("description", comp.get("description", ""))

    search_prompt = f"""Search the web for Canadian grant programs that would be relevant for this company:

Company: {comp.get('name', '')}
Sector: {sector} / {sub_sector}
Product: {product_desc[:300]}
Stage: {stage}
TRL: {trl}
HQ: {hq}

Search for these specific types of grants:
1. "{sector} grant Canada 2025 2026" - sector-specific federal grants
2. "IRAP {sub_sector or sector}" - NRC IRAP programs
3. "SR&ED {sector}" - SR&ED tax credit relevance
4. "SIF strategic innovation fund {sector}" - Strategic Innovation Fund
5. "{sector} funding program {province}" - provincial grants
6. "BDC {sector}" - Business Development Bank programs
7. "EDC export development {sector}" - if international sales potential
8. "Sustainable Development Technology Canada SDTC" - SDTC/cleantech funds
9. "Net Zero Accelerator {sector}" - Net Zero programs
10. "clean growth hub {sector}" - Clean Growth Hub programs

For each grant program found, provide:
- Program name
- Agency/organization
- Website URL
- Funding amount range
- Eligibility criteria
- Application status (open/closed/rolling)
- Next deadline if known
- Relevance to this specific company

Be thorough. Search multiple queries. Return ALL relevant programs found."""

    print(f"  Running web search for grant programs...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
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
    print(f"  Web search complete in {elapsed:.1f}s ({search_count} searches, {response.usage.input_tokens}in/{response.usage.output_tokens}out)")
    return result


# ---------------------------------------------------------------------------
# Sonnet eligibility analysis
# ---------------------------------------------------------------------------

ELIGIBILITY_SYSTEM = """You are a grants analyst for ClimateDoor, a climate venture advisory firm.
You are evaluating grant program eligibility for a specific company.

CRITICAL RULES:
1. Dollar amounts and deadlines MUST come from the research data, NOT from your training data.
   If data is unavailable, mark as "unverified".
2. Be precise about eligibility. If a criterion is uncertain, flag it explicitly.
3. Output valid JSON only. No markdown fences."""


def run_eligibility_analysis(client: anthropic.Anthropic, company: dict,
                             notion_grants: list[dict], web_research: str) -> list[dict]:
    """Score all grants against the company profile."""
    comp = company.get("company", {})
    product = company.get("product", {})

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
        "target_buyers": company.get("market", {}).get("target_buyers", []),
        "funding_history": company.get("funding", {}),
        "employee_count": company.get("team", {}).get("employee_count"),
    }

    notion_section = ""
    if notion_grants:
        notion_section = f"\n--- GRANTS FROM NOTION DATABASE ({len(notion_grants)} grants) ---\n{json.dumps(notion_grants, indent=2)}\n"

    user_msg = f"""Analyze grant eligibility for this company using all available data.

COMPANY:
{json.dumps(company_summary, indent=2)}

{notion_section}

--- WEB RESEARCH ON GRANT PROGRAMS ---
{web_research[:30000]}

Combine ALL grants found (from Notion DB and web research). De-duplicate by program name.
For Notion DB grants, prioritize the structured data (categories, eligible groups, region, intake status,
funding type, type of funding, website, application dates) over web research if there is a conflict.

For each grant, output a JSON object with:
- program_name: string
- agency: string (funding provider)
- program_url: string (verified website URL - use the "website" field from Notion if available)
- source: "notion_db" or "web_discovery"
- amount_range: string (from research data, or "unverified")
- funding_type: string (Federal, Provincial, Private, etc.)
- type_of_funding: string (Non-Repayable, Repayable, Tax Credit, Equity Investment, etc.)
- intake_status: "open" | "ongoing" | "closed" | "upcoming" | "unknown"
- next_deadline: date string or "rolling" or "unknown"
- application_start_date: date string or null
- application_end_date: date string or null
- eligibility_fit: "strong" | "moderate" | "weak" | "uncertain"
- eligibility_details: array of {{criterion: string, met: true/false/null, evidence: string}}
- strategic_value: 2-3 sentences on how this grant fits the company's strategy
- effort_estimate: "low" | "medium" | "high"
- confidence: 0.0-1.0
- confidence_reasoning: string
- notion_page_id: string or null (from Notion DB entries)
- notion_page_url: string or null (from Notion DB entries)

Output a JSON array. Be honest about gaps."""

    print(f"  Calling Sonnet for eligibility analysis...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=16000,
        system=ELIGIBILITY_SYSTEM,
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
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        print(f"  [ERROR] Failed to parse eligibility JSON")
        return []


def run_grants_as_bd_analysis(client: anthropic.Anthropic, company: dict) -> list[dict]:
    """Analyze grants-as-BD-tool: grants the company's CUSTOMERS can get."""
    comp = company.get("company", {})
    product = company.get("product", {})
    market = company.get("market", {})
    geo = comp.get("geography", {})

    search_prompt = f"""GRANTS-AS-BD-TOOL ANALYSIS

Company: {comp.get('name', '')}
Description: {comp.get('description', '')}
Product: {product.get('description', '')}
Target buyers: {json.dumps(market.get('target_buyers', []))}
Geography: {json.dumps(geo)}

The question is: "Can the company's END CUSTOMERS get grants that pay for this company's products/services?"

Think about who buys this company's products, then search for grant programs where:
- The CUSTOMER is the applicant (not the company itself)
- The company's products qualify as eligible expenses
- The grant effectively funds the customer's purchase

Search for relevant programs:
1. Customer industry modernization grants
2. Energy efficiency / sustainability adoption grants for buyers
3. Provincial green procurement incentives
4. Federal programs that fund adoption of clean technology
5. Municipal or institutional procurement support programs

For each opportunity found, provide:
- customer_type: who is the buyer
- grant_program: program name
- program_url: URL
- how_it_works: mechanics of the grants-as-BD model
- estimated_value: $ range
- confidence: 0-1

Output a JSON array. Be conservative - only include programs you have evidence for."""

    print(f"  Running grants-as-BD web search + analysis...")
    t0 = time.time()

    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=6000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": search_prompt}],
    )
    elapsed = time.time() - t0

    # Gather all text blocks
    text_parts = []
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            text_parts.append(block.text)

    raw = "\n".join(text_parts).strip()
    print(f"  Grants-as-BD analysis complete in {elapsed:.1f}s ({response.usage.input_tokens}in/{response.usage.output_tokens}out)")

    # Now ask Sonnet to extract structured JSON from the analysis
    extract_response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=4000,
        system="Extract structured JSON from the analysis below. Output ONLY a JSON array, no markdown.",
        messages=[{"role": "user", "content": f"""Extract grants-as-BD opportunities from this analysis as a JSON array.
Each element should have: type ("grants_as_bd"), customer_type, grant_program, program_url (or null),
customer_eligibility, how_it_works, estimated_value, confidence (0-1), confidence_reasoning.

Analysis:
{raw}"""}],
    )

    extract_raw = extract_response.content[0].text.strip()
    if extract_raw.startswith("```"):
        extract_raw = re.sub(r'^```\w*\n?', '', extract_raw)
        extract_raw = re.sub(r'\n?```$', '', extract_raw)

    try:
        return json.loads(extract_raw)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', extract_raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        print(f"  [WARN] Failed to parse grants-as-BD JSON")
        return []


# ---------------------------------------------------------------------------
# Add web-discovered grants to Notion
# ---------------------------------------------------------------------------

def create_grant_in_notion(grant: dict, company_name: str) -> str | None:
    """Create a new grant page in the Notion grant database.

    Returns the Notion page ID if successful, None otherwise.
    """
    if not NOTION_TOKEN or not NOTION_GRANT_DB:
        return None

    program_name = grant.get("program_name", "Unknown Program")

    # Build properties
    properties = {
        "Grant Name": {
            "title": [{"text": {"content": program_name[:100]}}],
        },
    }

    # Add URL if available
    url = grant.get("program_url", "")
    if url and url.startswith("http"):
        properties["Website"] = {"url": url}

    # Map funding_type to multi_select
    funding_type = grant.get("funding_type", "")
    if funding_type:
        properties["Funding Type"] = {
            "multi_select": [{"name": funding_type}],
        }

    # Map type_of_funding to multi_select
    type_of_funding = grant.get("type_of_funding", "")
    if type_of_funding:
        properties["Type of Funding"] = {
            "multi_select": [{"name": type_of_funding}],
        }

    # Set Eligible Groups to For-Profit by default
    properties["Eligible Groups"] = {
        "multi_select": [{"name": "For-Profit"}],
    }

    # Set Intake to unknown/unverified
    properties["Intake - NEW"] = {
        "multi_select": [{"name": "Ongoing"}],
    }

    try:
        body = {
            "parent": {"database_id": NOTION_GRANT_DB},
            "properties": properties,
            "children": [
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "\u26a0\ufe0f"},
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"AI Discovered - Unverified. Found during playbook generation for {company_name}. Needs Sophie review.",
                                },
                            }
                        ],
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"Agency: {grant.get('agency', 'Unknown')}\nAmount: {grant.get('amount_range', 'Unknown')}\nEligibility: {grant.get('eligibility_fit', 'Unknown')} fit\nStrategic Value: {grant.get('strategic_value', '')}",
                                },
                            }
                        ],
                    },
                },
            ],
        }

        r = req_lib.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json=body,
            timeout=15,
        )

        if r.status_code == 200:
            page_id = r.json().get("id", "")
            return page_id
        else:
            print(f"    [WARN] Failed to create Notion page for '{program_name}': {r.status_code} {r.text[:200]}")
            return None

    except Exception as e:
        print(f"    [WARN] Failed to create Notion page for '{program_name}': {e}")
        return None


def add_web_grants_to_notion(grants: list[dict], company_name: str) -> int:
    """Add web-discovered grants to Notion DB. Returns count of grants added."""
    web_grants = [g for g in grants if g.get("source") == "web_discovery"]
    if not web_grants:
        return 0

    added = 0
    for grant in web_grants:
        page_id = create_grant_in_notion(grant, company_name)
        if page_id:
            grant["notion_page_id"] = page_id
            added += 1
    return added


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_step3(slug: str) -> Path:
    data_dir = SKILL_ROOT / "data" / slug
    step1_path = data_dir / "step1-company.json"
    output_path = data_dir / "step3-grants.json"

    if not step1_path.exists():
        print(f"ERROR: {step1_path} not found. Run Step 1 first.")
        sys.exit(1)

    with open(step1_path) as f:
        company = json.load(f)

    comp = company.get("company", {})
    geo = comp.get("geography", {})
    print(f"=" * 60)
    print(f"STEP 3: Grant Scanning (Self-Contained)")
    print(f"Company: {comp.get('name', 'Unknown')}")
    print(f"Sector:  {comp.get('sector', 'Unknown')}")
    print(f"Sub-sector: {comp.get('sub_sector', 'Unknown')}")
    print(f"HQ:      {geo.get('hq', 'Unknown')}")
    print(f"Output:  {output_path}")
    print(f"=" * 60)

    client = anthropic.Anthropic()

    # Phase 1: Query Notion with proper filtering
    print(f"\n[Phase 1] Querying Notion grant database...")
    notion_grants = query_notion_grants(
        sector=comp.get("sector", ""),
        sub_sector=comp.get("sub_sector", ""),
        geography=geo,
    )

    # Phase 2: Web search for grants
    print(f"\n[Phase 2] Web searching for grant programs...")
    web_research = search_grants_web(client, company)

    # Phase 3: Eligibility analysis
    print(f"\n[Phase 3] Running eligibility analysis...")
    grants_analyzed = run_eligibility_analysis(client, company, notion_grants, web_research)
    print(f"  Analyzed {len(grants_analyzed)} grants")

    # Phase 4: Grants-as-BD-tool
    print(f"\n[Phase 4] Running grants-as-BD-tool analysis...")
    grants_as_bd = run_grants_as_bd_analysis(client, company)
    print(f"  Found {len(grants_as_bd)} grants-as-BD opportunities")

    # Phase 5: Add web-discovered grants to Notion
    print(f"\n[Phase 5] Adding web-discovered grants to Notion...")
    added_count = add_web_grants_to_notion(grants_analyzed, comp.get("name", slug))
    print(f"  Added {added_count} new grants to Notion DB")

    # Phase 6: Assemble output
    output = {
        "company": comp.get("name", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": SONNET_MODEL,
        "notion_db_id": NOTION_GRANT_DB,
        "pipeline_stats": {
            "notion_grants_queried": len(notion_grants),
            "web_discovered_grants": sum(1 for g in grants_analyzed if g.get("source") == "web_discovery"),
            "total_evaluated": len(grants_analyzed),
            "strong_fit": sum(1 for g in grants_analyzed if g.get("eligibility_fit") == "strong"),
            "moderate_fit": sum(1 for g in grants_analyzed if g.get("eligibility_fit") == "moderate"),
            "weak_fit": sum(1 for g in grants_analyzed if g.get("eligibility_fit") == "weak"),
            "grants_as_bd_opportunities": len(grants_as_bd),
            "added_to_notion": added_count,
        },
        "direct_grants": grants_analyzed,
        "grants_as_bd": grants_as_bd,
        "new_programs_for_sophie": [
            g for g in grants_analyzed
            if g.get("source") == "web_discovery"
        ],
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"STEP 3 COMPLETE")
    print(f"  Output: {output_path}")
    print(f"  Notion DB grants: {len(notion_grants)}")
    print(f"  Direct grants: {len(grants_analyzed)}")
    print(f"    Strong fit: {output['pipeline_stats']['strong_fit']}")
    print(f"    Moderate fit: {output['pipeline_stats']['moderate_fit']}")
    print(f"    Weak fit: {output['pipeline_stats']['weak_fit']}")
    print(f"  Grants-as-BD: {len(grants_as_bd)}")
    print(f"  New programs for Sophie: {len(output['new_programs_for_sophie'])}")
    print(f"  Added to Notion: {added_count}")
    print(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step3_grant_scanning.py <company-slug>")
        print("Example: python3 step3_grant_scanning.py fuse-power")
        sys.exit(1)

    slug = sys.argv[1]
    output = run_step3(slug)
    print(f"\nDone. Output at: {output}")
