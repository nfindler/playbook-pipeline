#!/usr/bin/env python3
"""
Step 2b: Apollo Contact Matchmaking
Model: Sonnet (named-target extraction + fit notes, ~$0.10)
Input: data/[slug]/step1-company.json, step4-market.json, step6-synthesis.json
Output: data/[slug]/step2b-contacts.json

Phase 1: Load buyer intelligence from step4 + step6 (named orgs, strategy pillars)
Phase 2: Sonnet extracts named targets + broad segment types
Phase 3: Apollo per-org search for named targets (5 results each)
Phase 4: Apollo broad search per segment (25 results, deduped)
Investor search unchanged.
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
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import anthropic
import requests

SONNET_MODEL = "claude-sonnet-4-6"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "x-api-key": APOLLO_API_KEY,
}

# ---------------------------------------------------------------------------
# Sector-to-title mappings (from SKILL-apollo-matchmaking.md)
# ---------------------------------------------------------------------------

BUYER_TITLES_BY_SECTOR = {
    "Buildings & Smart Cities": [
        "VP Development", "VP Construction", "VP Procurement", "Director of Procurement",
        "Director of Construction", "VP Sustainability", "Director of Sustainability",
        "Chief Sustainability Officer",
    ],
    "Energy & Renewables": [
        "VP Energy", "VP Procurement", "Director of Energy", "VP Operations",
        "VP Sustainability", "Chief Sustainability Officer", "Director of Procurement",
    ],
    "Transportation & Mobility": [
        "VP Fleet", "VP Operations", "VP Procurement", "Director of Logistics",
        "VP Sustainability", "Director of Transportation",
    ],
    "Agriculture & Forestry": [
        "VP Operations", "VP Procurement", "Director of Sustainability",
        "VP Agriculture", "Director of Procurement",
    ],
    "Waste & Circular Economy": [
        "VP Sustainability", "VP Operations", "Director of Procurement",
        "VP Supply Chain", "Chief Sustainability Officer",
    ],
    "Water": [
        "VP Operations", "VP Infrastructure", "Director of Procurement",
        "VP Water", "Director of Sustainability",
    ],
    "Carbon Solutions": [
        "VP Sustainability", "Chief Sustainability Officer", "VP ESG",
        "Director of Carbon", "VP Procurement",
    ],
    "Industrial & Manufacturing": [
        "VP Procurement", "VP Operations", "VP Manufacturing",
        "Director of Procurement", "VP Sustainability", "VP Supply Chain",
    ],
    "Sustainable Fashion & Textiles": [
        "VP Procurement", "VP Sustainability", "Director of Sourcing",
        "VP Supply Chain", "Chief Sustainability Officer",
    ],
    "Healthcare & Medical Devices": [
        "VP Procurement", "Director of Procurement", "VP Operations",
        "VP Sustainability", "Chief Sustainability Officer", "Director of Facilities",
    ],
    "Energy & Storage": [
        "VP Energy", "VP Procurement", "VP Operations", "Director of Energy",
        "VP Sustainability", "Chief Sustainability Officer", "Director of Procurement",
        "VP Fleet", "Director of Facilities",
    ],
    "Clean Energy": [
        "VP Energy", "VP Procurement", "Director of Energy", "VP Operations",
        "VP Sustainability", "Chief Sustainability Officer", "Director of Procurement",
    ],
    "Construction Technology": [
        "VP Development", "VP Construction", "VP Procurement", "Director of Procurement",
        "Director of Construction", "VP Sustainability", "Director of Sustainability",
        "Chief Sustainability Officer",
    ],
    "Circular Economy": [
        "VP Sustainability", "VP Operations", "Director of Procurement",
        "VP Supply Chain", "Chief Sustainability Officer", "VP Procurement",
    ],
}

UNIVERSAL_BUYER_TITLES = [
    "VP Procurement", "Director of Procurement",
    "VP Sustainability", "Chief Sustainability Officer",
]

INVESTOR_TITLES = [
    "Partner", "Managing Partner", "General Partner", "Principal",
    "Investment Director", "Founding Partner", "Managing Director",
]

INVESTOR_BASE_KEYWORDS = [
    "venture capital", "cleantech", "climate tech", "impact fund", "impact investing",
]

INVESTOR_SECTOR_KEYWORDS = {
    "Buildings & Smart Cities": ["green construction", "sustainable building", "proptech"],
    "Energy & Renewables": ["clean energy", "renewable energy", "energy transition"],
    "Transportation & Mobility": ["mobility", "transport", "EV", "fleet electrification"],
    "Agriculture & Forestry": ["agtech", "sustainable agriculture", "forestry"],
    "Waste & Circular Economy": ["circular economy", "waste management", "recycling"],
    "Water": ["water technology", "water treatment"],
    "Carbon Solutions": ["carbon capture", "carbon removal", "carbon credits"],
    "Industrial & Manufacturing": ["industrial decarbonization", "advanced manufacturing"],
    "Sustainable Fashion & Textiles": ["sustainable fashion", "textile innovation"],
    "Healthcare & Medical Devices": ["healthtech", "medical devices", "healthcare innovation"],
    "Energy & Storage": ["clean energy", "renewable energy", "energy transition", "energy storage", "battery"],
    "Clean Energy": ["clean energy", "renewable energy", "energy transition"],
    "Construction Technology": ["green construction", "sustainable building", "proptech", "construction technology"],
    "Circular Economy": ["circular economy", "waste management", "recycling", "sustainable materials"],
}

BUYER_KEYWORD_MAP = {
    "real estate developers": ["real estate developer", "property development", "residential construction", "housing developer"],
    "modular builders": ["modular construction", "prefab", "offsite construction", "modular building"],
    "municipalities": ["municipality", "city government", "local government", "public works"],
    "non-profit housing": ["affordable housing", "non-profit housing", "community housing", "social housing"],
    "utilities": ["utility", "electric utility", "power company", "energy provider"],
    "mining companies": ["mining", "mineral extraction", "resource company"],
    "agricultural operations": ["agriculture", "farming", "agribusiness", "food production"],
    "hospitals / healthcare": ["hospital", "healthcare", "health system", "medical center"],
}

# Geography expansion
GEO_EXPANSION = {
    "British Columbia": ["British Columbia, Canada", "Alberta, Canada"],
    "BC": ["British Columbia, Canada", "Alberta, Canada"],
    "Alberta": ["Alberta, Canada", "British Columbia, Canada"],
    "AB": ["Alberta, Canada", "British Columbia, Canada"],
    "Quebec": ["Quebec, Canada", "Ontario, Canada"],
    "QC": ["Quebec, Canada", "Ontario, Canada"],
    "Ontario": ["Ontario, Canada", "Quebec, Canada"],
    "ON": ["Ontario, Canada", "Quebec, Canada"],
    "Manitoba": ["Manitoba, Canada", "Saskatchewan, Canada"],
    "MB": ["Manitoba, Canada", "Saskatchewan, Canada"],
    "Saskatchewan": ["Saskatchewan, Canada", "Alberta, Canada"],
    "SK": ["Saskatchewan, Canada", "Alberta, Canada"],
    "Nova Scotia": ["Nova Scotia, Canada", "New Brunswick, Canada"],
    "NS": ["Nova Scotia, Canada", "New Brunswick, Canada"],
    "New Brunswick": ["New Brunswick, Canada", "Nova Scotia, Canada"],
    "NB": ["New Brunswick, Canada", "Nova Scotia, Canada"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_province(hq: str) -> str:
    """Extract province from HQ string like 'Montreal, Quebec, Canada'."""
    if not hq:
        return ""
    parts = [p.strip() for p in hq.split(",")]
    # Try second-to-last part (before country)
    if len(parts) >= 3:
        return parts[-2]
    if len(parts) == 2:
        return parts[0]
    return hq


def get_buyer_locations(geography: dict) -> tuple[list[str], list[str]]:
    """Return (broad_locations, tight_locations) for buyer search."""
    hq = geography.get("hq", "Canada")
    province = extract_province(hq)

    expansion = geography.get("expansion_markets", [])

    # Tight: primary geo only
    tight = []
    if province and province != "Canada":
        tight.append(f"{province}, Canada")
    else:
        tight.append("Canada")

    # Broad: primary + expanded
    broad = list(tight)
    if province in GEO_EXPANSION:
        for loc in GEO_EXPANSION[province]:
            if loc not in broad:
                broad.append(loc)

    for market in expansion:
        if market not in broad:
            broad.append(market)

    return broad, tight


def get_buyer_titles(sector: str) -> tuple[list[str], list[str]]:
    """Return (all_titles, top_8_titles) for buyer search."""
    sector_titles = BUYER_TITLES_BY_SECTOR.get(sector, [])
    all_titles = list(dict.fromkeys(sector_titles + UNIVERSAL_BUYER_TITLES))
    top_8 = all_titles[:8]
    return all_titles, top_8


def get_buyer_keywords(target_buyers: list, sector: str, climate_types: list = None) -> tuple[list[str], list[str]]:
    """Return (all_keywords, top_6_keywords) for buyer org keyword tags."""
    keywords = []
    for buyer in target_buyers:
        buyer_lower = buyer.lower() if isinstance(buyer, str) else ""
        for key, kws in BUYER_KEYWORD_MAP.items():
            if key in buyer_lower or buyer_lower in key:
                keywords.extend(kws)
                break
        else:
            # Use the buyer segment text directly as keyword
            if buyer_lower and "indigenous" not in buyer_lower:
                keywords.append(buyer_lower)

    # Sector-derived fallback keywords (always add these for breadth)
    SECTOR_BUYER_KEYWORDS = {
        "Clean Energy": ["utility", "energy provider", "solar installer", "renewable energy", "power company", "energy services"],
        "Energy & Renewables": ["utility", "energy provider", "power company", "energy services"],
        "Energy & Storage": ["utility", "fleet management", "energy provider", "power company", "electric vehicle"],
        "Construction Technology": ["construction", "general contractor", "real estate developer", "property development", "engineering firm"],
        "Circular Economy": ["sustainability", "corporate procurement", "healthcare", "dental", "retail"],
        "Buildings & Smart Cities": ["real estate developer", "property development", "construction", "housing"],
        "Transportation & Mobility": ["fleet management", "logistics", "transportation", "transit authority"],
        "Agriculture & Forestry": ["agriculture", "farming", "agribusiness", "food production"],
        "Water": ["utility", "water treatment", "municipal", "public works"],
        "Carbon Solutions": ["energy company", "oil gas", "manufacturing", "heavy industry"],
        "Industrial & Manufacturing": ["manufacturing", "industrial", "procurement", "supply chain"],
    }

    # Always include sector-derived keywords for breadth
    sector_fallback = SECTOR_BUYER_KEYWORDS.get(sector, [])
    keywords.extend(sector_fallback)

    if climate_types:
        for ct in climate_types[:3]:
            if isinstance(ct, str) and ct.lower() not in [k.lower() for k in keywords]:
                keywords.append(ct.lower())

    all_kw = list(dict.fromkeys(keywords))
    top_6 = all_kw[:6]
    return all_kw, top_6


def get_investor_keywords(sector: str, climate_types: list = None, has_indigenous: bool = False) -> list[str]:
    """Return keyword tags for investor org search."""
    keywords = list(INVESTOR_BASE_KEYWORDS)
    sector_kw = INVESTOR_SECTOR_KEYWORDS.get(sector, [])
    keywords.extend(sector_kw)
    if has_indigenous:
        keywords.extend(["indigenous capital", "indigenous investment", "reconciliation"])
    return list(dict.fromkeys(keywords))


def get_investor_locations(geography: dict) -> list[str]:
    """Investor geography is broader -- default Canada."""
    locations = ["Canada"]
    expansion = geography.get("expansion_markets", [])
    for market in expansion:
        if "united states" in market.lower() or "us" in market.lower():
            locations.append("United States")
        if "europe" in market.lower() or "eu" in market.lower():
            locations.append("Europe")
    return locations


# ---------------------------------------------------------------------------
# Buyer intelligence extraction (Phases 1-2)
# ---------------------------------------------------------------------------

def load_buyer_intelligence(slug: str) -> dict:
    """Phase 1: Load buyer intelligence from step4-market.json and step6-synthesis.json."""
    data_dir = SKILL_ROOT / "data" / slug
    intel = {"buyer_segments": [], "strategy_pillars": {}, "creative_opportunities": []}

    s4_path = data_dir / "step4-market.json"
    if s4_path.exists():
        with open(s4_path) as f:
            s4 = json.load(f)
        intel["buyer_segments"] = s4.get("buyer_segments", [])

    s6_path = data_dir / "step6-synthesis.json"
    if s6_path.exists():
        with open(s6_path) as f:
            s6 = json.load(f)
        intel["strategy_pillars"] = s6.get("strategy_pillars", {})
        intel["creative_opportunities"] = s6.get("creative_opportunities", [])

    return intel


NAMED_TARGET_SYSTEM = """You extract named buyer targets from market intelligence for Apollo People Search.
Output ONLY valid JSON, no markdown fences.
Be precise: only include organizations explicitly named in the intelligence data."""


def extract_named_targets(client: anthropic.Anthropic, company: dict, intelligence: dict) -> dict:
    """Phase 2: Sonnet call to extract named orgs + broad segment types from buyer intelligence."""
    comp = company.get("company", {})
    company_name = comp.get("name", "")
    sector = comp.get("sector", "")

    # Build intelligence text
    segments_text = json.dumps(intelligence.get("buyer_segments", []), indent=1)
    pillars_text = json.dumps(intelligence.get("strategy_pillars", {}), indent=1)
    opps_text = json.dumps(intelligence.get("creative_opportunities", []), indent=1)

    user_msg = f"""Extract named buyer targets for {company_name} (sector: {sector}).

BUYER SEGMENTS (from market analysis):
{segments_text}

STRATEGY PILLARS:
{pillars_text}

CREATIVE OPPORTUNITIES:
{opps_text}

From the above intelligence, extract:

1. **named_targets**: Every specifically named organization mentioned as a potential buyer, partner, or customer. For each:
   - org_name: Exact organization name (e.g. "BC Hydro", "TransLink", "ChargePoint")
   - reason: Why this org is a target (1 sentence, reference the specific intelligence)
   - target_titles: 2-4 job titles of decision-makers to search for at this org
   - segment: Which buyer segment this org belongs to

2. **broad_segments**: 3-5 broad segment categories for discovering additional buyers beyond named targets. For each:
   - segment_name: Descriptive name (e.g. "Canadian Electric Utilities")
   - org_keywords: 3-6 Apollo keyword tags to find orgs in this segment
   - titles: 3-5 decision-maker titles to search

Output JSON:
{{
  "named_targets": [...],
  "broad_segments": [...]
}}"""

    print(f"  Extracting named targets via Sonnet...")
    t0 = time.time()

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4000,
            system=NAMED_TARGET_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        elapsed = time.time() - t0
        print(f"  Named targets extracted in {elapsed:.1f}s ({response.usage.input_tokens}in/{response.usage.output_tokens}out)")

        import re as _re
        if raw.startswith("```"):
            raw = _re.sub(r'^```\w*\n?', '', raw)
            raw = _re.sub(r'\n?```$', '', raw)

        result = json.loads(raw)
        named = result.get("named_targets", [])
        broad = result.get("broad_segments", [])
        print(f"  Found {len(named)} named targets, {len(broad)} broad segments")
        return result

    except Exception as e:
        print(f"  [WARN] Named target extraction failed: {e}")
        return {"named_targets": [], "broad_segments": []}


def search_named_targets(targets: list, geography: dict) -> tuple[list, int]:
    """Phase 3: Apollo search for each named target org. Returns (contacts, total_scanned)."""
    if not targets:
        return [], 0

    _, tight_locs = get_buyer_locations(geography)
    # Use broader Canada geography for named targets since we know the exact org
    locs = ["Canada"]
    for loc in tight_locs:
        if loc not in locs:
            locs.append(loc)

    all_contacts = []
    total_scanned = 0

    for t in targets[:15]:  # Cap at 15 named targets
        org_name = t.get("org_name", "")
        titles = t.get("target_titles", ["VP", "Director", "Chief"])
        segment = t.get("segment", "")
        reason = t.get("reason", "")

        if not org_name:
            continue

        payload = {
            "q_organization_name": org_name,
            "person_titles": titles[:4],
            "person_seniorities": ["vp", "c_suite", "director"],
            "per_page": 5,
            "page": 1,
        }

        print(f"  [named] Searching {org_name}...")
        resp = apollo_search(payload, f"named-{org_name[:20]}")
        scanned = resp.get("total_entries", 0)
        total_scanned += scanned
        people = resp.get("people", []) or []

        for p in people:
            c = extract_contact(p)
            c["type"] = "named_target"
            c["reason"] = reason
            c["segment"] = segment
            all_contacts.append(c)

        time.sleep(1)

    print(f"  [named] {len(all_contacts)} contacts from {len(targets)} orgs")
    return all_contacts, total_scanned


def search_broad_segments(segments: list, geography: dict, exclude_orgs: set) -> tuple[list, int]:
    """Phase 4: Apollo broad search per segment. Returns (contacts, total_scanned)."""
    if not segments:
        return [], 0

    broad_locs, _ = get_buyer_locations(geography)
    all_contacts = []
    total_scanned = 0

    for seg in segments[:5]:  # Cap at 5 segments
        seg_name = seg.get("segment_name", "")
        org_keywords = seg.get("org_keywords", [])
        titles = seg.get("titles", ["VP Procurement", "VP Operations", "Director"])

        if not org_keywords:
            continue

        payload = {
            "person_titles": titles[:5],
            "person_seniorities": ["vp", "c_suite", "director"],
            "person_locations": broad_locs,
            "q_organization_keyword_tags": org_keywords[:6],
            "organization_num_employees_ranges": ["51,200", "201,500", "501,1000", "1001,5000", "5001,10000"],
            "per_page": 25,
            "page": 1,
        }

        print(f"  [broad] Searching segment: {seg_name}...")
        resp = apollo_search(payload, f"broad-{seg_name[:20]}")
        scanned = resp.get("total_entries", 0)
        total_scanned += scanned
        people = resp.get("people", []) or []

        seg_contacts = []
        seen_orgs = set()
        for p in people:
            c = extract_contact(p)
            org_key = c["organization_name"].lower().strip()
            # Skip orgs already found as named targets, and deduplicate within segment
            if org_key in exclude_orgs or org_key in seen_orgs or not org_key:
                continue
            seen_orgs.add(org_key)
            c["type"] = "discovered"
            c["reason"] = ""
            c["segment"] = seg_name
            seg_contacts.append(c)

        # Take top 5 per segment by buyer priority
        seg_contacts.sort(key=buyer_priority, reverse=True)
        all_contacts.extend(seg_contacts[:5])

        time.sleep(1)

    print(f"  [broad] {len(all_contacts)} discovered contacts across {len(segments)} segments")
    return all_contacts, total_scanned


# ---------------------------------------------------------------------------
# Apollo API calls
# ---------------------------------------------------------------------------

def apollo_search(payload: dict, label: str = "") -> dict:
    """Call Apollo People Search. Returns raw JSON response."""
    if not APOLLO_API_KEY:
        print(f"  [SKIP] No APOLLO_API_KEY configured")
        return {"people": [], "pagination": {"total_entries": 0}}

    try:
        r = requests.post(APOLLO_SEARCH_URL, headers=APOLLO_HEADERS, json=payload, timeout=15)
        if r.status_code == 429:
            print(f"  [{label}] Rate limited, waiting 5s...")
            time.sleep(5)
            r = requests.post(APOLLO_SEARCH_URL, headers=APOLLO_HEADERS, json=payload, timeout=15)
        if r.status_code != 200:
            print(f"  [{label}] Apollo returned {r.status_code}: {r.text[:200]}")
            return {"people": [], "total_entries": 0}
        data = r.json()
        # Normalize: api_search puts total_entries at top level, not in pagination
        if "total_entries" not in data:
            data["total_entries"] = data.get("pagination", {}).get("total_entries", 0)
        return data
    except Exception as e:
        print(f"  [{label}] Apollo request failed: {e}")
        return {"people": [], "total_entries": 0}


def extract_contact(person: dict) -> dict:
    """Extract a contact dict from Apollo person result."""
    first = person.get("first_name", "")
    last = person.get("last_name", person.get("last_name_obfuscated", ""))
    display = f"{first} {last}".strip()
    ini = ""
    if first:
        ini += first[0].upper()
    if last:
        ini += last[0].upper()

    org = person.get("organization", {}) or {}
    return {
        "first_name": first,
        "last_name": last,
        "display_name": display,
        "initials": ini or "?",
        "title": person.get("title", ""),
        "organization_name": org.get("name", ""),
        "organization_id": person.get("organization_id", ""),
        # api_search returns has_city/has_state/has_country flags, not values
        "city": person.get("city", ""),
        "state": person.get("state", ""),
        "country": person.get("country", ""),
        "apollo_id": person.get("id", ""),
        "has_email": bool(person.get("has_email")),
        "employee_count": org.get("estimated_num_employees"),
    }


def deduplicate_contacts(contacts: list, priority_fn) -> list:
    """Deduplicate to one contact per org, pick best per priority_fn. Return up to 20."""
    by_org = {}
    for c in contacts:
        org = c["organization_name"]
        if not org:
            continue
        org_key = org.lower().strip()
        if org_key not in by_org or priority_fn(c) > priority_fn(by_org[org_key]):
            by_org[org_key] = c
    # Sort by priority descending, take 20
    sorted_contacts = sorted(by_org.values(), key=priority_fn, reverse=True)
    return sorted_contacts[:20]


def buyer_priority(c: dict) -> int:
    """Score buyer contact for dedup priority. VP > Director > C-suite."""
    title = (c.get("title") or "").lower()
    score = 0
    if "vp" in title or "vice president" in title:
        score += 30
    elif "svp" in title or "senior vice" in title:
        score += 28
    elif "director" in title:
        score += 20
    elif "chief" in title or "cso" in title or "coo" in title:
        score += 15
    else:
        score += 5
    # Bonus for procurement/sustainability/development titles
    for kw in ["procurement", "sustainability", "development", "construction"]:
        if kw in title:
            score += 10
            break
    if c.get("has_email"):
        score += 3
    return score


def investor_priority(c: dict) -> int:
    """Score investor contact for dedup priority. Managing Partner > GP > Partner > Principal."""
    title = (c.get("title") or "").lower()
    score = 0
    if "managing partner" in title or "managing director" in title:
        score += 30
    elif "general partner" in title or "founding partner" in title:
        score += 25
    elif "partner" in title:
        score += 20
    elif "principal" in title:
        score += 15
    elif "investment director" in title:
        score += 12
    else:
        score += 5
    if c.get("has_email"):
        score += 3
    return score


# ---------------------------------------------------------------------------
# Search orchestration
# ---------------------------------------------------------------------------

def search_category(category: str, broad_payload: dict, tight_payload: dict) -> dict:
    """Run broad + tight (2 pages) search for one category. Returns concentric + contacts."""
    # 1) Broad search (per_page=1 for total_entries only)
    broad_payload["per_page"] = 1
    broad_payload["page"] = 1
    print(f"  [{category}] Broad search...")
    broad_resp = apollo_search(broad_payload, f"{category}-broad")
    scanned = broad_resp.get("total_entries", 0)
    print(f"  [{category}] Scanned: {scanned:,}")
    time.sleep(1)

    # 2) Tight search page 1
    tight_payload["per_page"] = 25
    tight_payload["page"] = 1
    print(f"  [{category}] Tight search page 1...")
    tight1 = apollo_search(tight_payload, f"{category}-tight-p1")
    targeted = tight1.get("total_entries", 0)
    people_1 = tight1.get("people", []) or []
    print(f"  [{category}] Targeted: {targeted:,}, page 1: {len(people_1)} results")
    time.sleep(1)

    # 3) Tight search page 2
    tight_payload["page"] = 2
    print(f"  [{category}] Tight search page 2...")
    tight2 = apollo_search(tight_payload, f"{category}-tight-p2")
    people_2 = tight2.get("people", []) or []
    print(f"  [{category}] Page 2: {len(people_2)} results")

    all_people = people_1 + people_2
    contacts = [extract_contact(p) for p in all_people]

    # Deduplicate
    priority_fn = buyer_priority if category == "buyers" else investor_priority
    deduped = deduplicate_contacts(contacts, priority_fn)
    print(f"  [{category}] Unique firms after dedup: {len(deduped)}")

    # If <20 unique firms, try page 3
    if len(deduped) < 20 and targeted > 50:
        time.sleep(1)
        tight_payload["page"] = 3
        print(f"  [{category}] Page 3 (need more unique firms)...")
        tight3 = apollo_search(tight_payload, f"{category}-tight-p3")
        people_3 = tight3.get("people", []) or []
        extra = [extract_contact(p) for p in people_3]
        all_contacts = contacts + extra
        deduped = deduplicate_contacts(all_contacts, priority_fn)
        print(f"  [{category}] After page 3: {len(deduped)} unique firms")

    # If still 0 results, try broadening by removing keyword tags
    if len(deduped) == 0 and targeted == 0:
        kw_tags = tight_payload.get("q_organization_keyword_tags", [])
        if len(kw_tags) > 2:
            print(f"  [{category}] 0 results, retrying with fewer keywords...")
            tight_payload["q_organization_keyword_tags"] = kw_tags[:len(kw_tags) - 2]
            tight_payload["page"] = 1
            time.sleep(1)
            retry = apollo_search(tight_payload, f"{category}-retry")
            targeted = retry.get("total_entries", 0)
            retry_people = retry.get("people", []) or []
            retry_contacts = [extract_contact(p) for p in retry_people]
            deduped = deduplicate_contacts(retry_contacts, priority_fn)
            print(f"  [{category}] Retry: {targeted:,} targeted, {len(deduped)} unique firms")

    return {
        "concentric": {
            "scanned": scanned,
            "targeted": targeted,
            "previewed": len(deduped),
        },
        "contacts": deduped,
    }


def run_buyer_search(company: dict, slug: str = "") -> dict:
    """Build and execute buyer search using named-target + broad discovery approach."""
    comp = company.get("company", {})
    geography = comp.get("geography", {})

    client = anthropic.Anthropic()

    # Phase 1: Load buyer intelligence from step4 + step6
    print(f"\n  [Phase 1] Loading buyer intelligence...")
    intelligence = load_buyer_intelligence(slug)
    n_segs = len(intelligence.get("buyer_segments", []))
    print(f"  Found {n_segs} buyer segments in step4")

    # Phase 2: Extract named targets via Sonnet
    print(f"\n  [Phase 2] Extracting named targets...")
    extraction = extract_named_targets(client, company, intelligence)
    named_targets = extraction.get("named_targets", [])
    broad_segments = extraction.get("broad_segments", [])

    # Phase 3: Search named targets on Apollo
    print(f"\n  [Phase 3] Searching named targets on Apollo...")
    named_contacts, named_scanned = search_named_targets(named_targets, geography)

    # Build exclude set from named target orgs
    exclude_orgs = {c["organization_name"].lower().strip() for c in named_contacts if c.get("organization_name")}

    # Phase 4: Broad segment discovery
    print(f"\n  [Phase 4] Broad segment discovery...")
    broad_contacts, broad_scanned = search_broad_segments(broad_segments, geography, exclude_orgs)

    # Merge and group by segment
    all_contacts = named_contacts + broad_contacts
    total_scanned = named_scanned + broad_scanned

    # Group contacts by segment
    segment_map = {}
    for c in all_contacts:
        seg = c.get("segment", "Other")
        if seg not in segment_map:
            segment_map[seg] = []
        segment_map[seg].append(c)

    # Deduplicate within each segment (one contact per org)
    segments = []
    total_previewed = 0
    for seg_name, contacts in segment_map.items():
        by_org = {}
        for c in contacts:
            org_key = c["organization_name"].lower().strip()
            if not org_key:
                continue
            if org_key not in by_org or buyer_priority(c) > buyer_priority(by_org[org_key]):
                by_org[org_key] = c
        deduped = sorted(by_org.values(), key=buyer_priority, reverse=True)
        total_previewed += len(deduped)
        segments.append({
            "segment_name": seg_name,
            "contacts": deduped,
        })

    # Also build flat contact list for backward compat
    flat_contacts = []
    for seg in segments:
        flat_contacts.extend(seg["contacts"])
    flat_contacts.sort(key=buyer_priority, reverse=True)
    flat_contacts = flat_contacts[:20]

    print(f"  [buyers] {len(segments)} segments, {total_previewed} total contacts")

    return {
        "concentric": {
            "scanned": total_scanned,
            "targeted": len(all_contacts),
            "previewed": total_previewed,
        },
        "segments": segments,
        "contacts": flat_contacts,
    }


def run_investor_search(company: dict) -> dict:
    """Build and execute investor search."""
    comp = company.get("company", {})
    sector = comp.get("sector", "")
    geography = comp.get("geography", {})
    has_indigenous = comp.get("has_indigenous_alignment", False)

    investor_kw = get_investor_keywords(sector, comp.get("climate_sector_types"), has_indigenous)
    investor_locs = get_investor_locations(geography)

    # Broad: wider keywords, no employee filter
    broad_payload = {
        "person_titles": ["Partner", "Managing Director", "Principal", "Managing Partner", "General Partner", "Investment Director"],
        "person_locations": investor_locs,
        "q_organization_keyword_tags": ["cleantech", "climate", "sustainability", "clean energy", "impact investing", "renewable energy"],
    }

    # Tight: sector-specific keywords + fund-size filter
    tight_payload = {
        "person_titles": INVESTOR_TITLES[:6],
        "person_locations": investor_locs,
        "q_organization_keyword_tags": investor_kw[:8],
        "organization_num_employees_ranges": ["1,10", "11,50", "51,200"],
    }

    return search_category("investors", broad_payload, tight_payload)


# ---------------------------------------------------------------------------
# Fit notes (single Sonnet call for all 40 contacts)
# ---------------------------------------------------------------------------

FIT_NOTE_SYSTEM = """You generate fit notes for a contact matchmaking system.
Each fit note must be 1-2 sentences explaining why this specific contact/organization
is a good match for the target company. Be SPECIFIC, referencing actual sector alignment,
geography, or product fit. Never generic.

CRITICAL: Never mention Apollo. This is "ClimateDoor Intelligence".
Output ONLY valid JSON, no markdown fences."""


def generate_fit_notes(client: anthropic.Anthropic, company: dict,
                       buyers: list, investors: list) -> tuple[list, list]:
    """Generate fit notes for all contacts in a single Sonnet call."""
    comp = company.get("company", {})
    product = company.get("product", {})

    company_summary = {
        "name": comp.get("name", ""),
        "sector": comp.get("sector", ""),
        "description": comp.get("description", "")[:300],
        "product": product.get("description", "")[:300],
        "geography": comp.get("geography", {}).get("hq", ""),
        "stage": comp.get("stage", ""),
        "climate_types": comp.get("climate_sector_types", [])[:5],
    }

    # Build contact summaries
    contact_list = []
    for i, c in enumerate(buyers):
        entry = {
            "idx": f"B{i}",
            "type": "buyer",
            "name": c["display_name"],
            "title": c["title"],
            "org": c["organization_name"],
            "city": c.get("city", ""),
        }
        # Include intelligence reason for named targets so Sonnet can reference it
        if c.get("reason"):
            entry["intel_reason"] = c["reason"]
        if c.get("segment"):
            entry["segment"] = c["segment"]
        contact_list.append(entry)
    for i, c in enumerate(investors):
        contact_list.append({
            "idx": f"I{i}",
            "type": "investor",
            "name": c["display_name"],
            "title": c["title"],
            "org": c["organization_name"],
            "city": c.get("city", ""),
        })

    if not contact_list:
        return buyers, investors

    user_msg = f"""Generate fit notes for these contacts matched to {comp.get('name', '')}.

COMPANY:
{json.dumps(company_summary, indent=2)}

CONTACTS:
{json.dumps(contact_list, indent=2)}

For each contact, output a JSON object with:
- idx: the contact index (B0, B1, ..., I0, I1, ...)
- fit_note: 1-2 sentences, SPECIFIC to why this org/person matches the company above.

For BUYERS: explain why the buyer's org would want to purchase {comp.get('name', '')}'s product.
If the contact has an "intel_reason" field, reference that specific intelligence in the fit note.
For INVESTORS: explain why the fund's thesis aligns with {comp.get('name', '')}'s stage and sector.

Output a JSON array of objects. No markdown."""

    print(f"  Generating fit notes for {len(contact_list)} contacts...")
    t0 = time.time()

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=6000,
            system=FIT_NOTE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        elapsed = time.time() - t0
        print(f"  Fit notes generated in {elapsed:.1f}s ({response.usage.input_tokens}in/{response.usage.output_tokens}out)")

        import re
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)

        try:
            notes = json.loads(raw)
        except json.JSONDecodeError:
            # Try to salvage partial JSON (truncated array)
            import re
            # Find all complete objects in the truncated array
            matches = re.findall(r'\{[^{}]*"idx"\s*:\s*"[^"]+"\s*,[^{}]*"fit_note"\s*:\s*"[^"]*"[^{}]*\}', raw)
            notes = [json.loads(m) for m in matches]
            print(f"  [WARN] Salvaged {len(notes)} fit notes from truncated JSON")

        note_map = {n["idx"]: n["fit_note"] for n in notes if "idx" in n and "fit_note" in n}

        for i, c in enumerate(buyers):
            c["fit_note"] = note_map.get(f"B{i}", "")
        for i, c in enumerate(investors):
            c["fit_note"] = note_map.get(f"I{i}", "")

    except Exception as e:
        print(f"  [WARN] Fit note generation failed: {e}")
        # Leave fit_note empty

    return buyers, investors


# ---------------------------------------------------------------------------
# HubSpot field mapping (stored for future Save button)
# ---------------------------------------------------------------------------

def build_hubspot_mapping(company_name: str, sector: str, stage: str) -> dict:
    return {
        "icp2_defaults": {
            "avatar___cloned_": "ICP2: Investor",
            "stage_of_company_preferred": stage,
            "preferred_region": "Canada",
            "investor_warmth": "Cold",
            "nurture_tier": "Tier 4 - Unknown",
            "icp3__owned_by_cd_cli": "ClimateDoor",
            "lead_source": "Apollo",
        },
        "icp3_defaults": {
            "avatar___cloned_": "ICP3: Partner / Buyer",
            "nurture_tier": "Tier 4 - Unknown",
            "icp3__sourced_by_cd_cli": "ClimateDoor",
            "lead_source": "Apollo",
            "icp3_matched_icp1": company_name,
            "icp3_deal_stage": "Match Identified",
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_step2b(slug: str) -> Path:
    data_dir = SKILL_ROOT / "data" / slug
    step1_path = data_dir / "step1-company.json"
    output_path = data_dir / "step2b-contacts.json"

    if not step1_path.exists():
        print(f"ERROR: {step1_path} not found. Run Step 1 first.")
        sys.exit(1)

    with open(step1_path) as f:
        company = json.load(f)

    comp = company.get("company", {})
    print(f"{'=' * 60}")
    print(f"STEP 2b: Apollo Contact Matchmaking")
    print(f"Company: {comp.get('name', 'Unknown')}")
    print(f"Sector:  {comp.get('sector', 'Unknown')}")
    print(f"HQ:      {comp.get('geography', {}).get('hq', 'Unknown')}")
    print(f"Output:  {output_path}")
    print(f"{'=' * 60}")

    if not APOLLO_API_KEY:
        print("  [ERROR] APOLLO_API_KEY not set. Outputting empty contacts.")
        output = {
            "buyers": {"concentric": {"scanned": 0, "targeted": 0, "previewed": 0}, "segments": [], "contacts": []},
            "investors": {"concentric": {"scanned": 0, "targeted": 0, "previewed": 0}, "contacts": []},
            "hubspot_field_mapping": build_hubspot_mapping(
                comp.get("name", ""), comp.get("sector", ""), comp.get("stage", "")
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": SONNET_MODEL,
            "credits_consumed": 0,
        }
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        return output_path

    # Run buyer search (named-target + broad discovery, sequential -- uses Sonnet)
    print(f"\n[Phase 1-4] Running buyer search (named targets + broad discovery)...")
    t0 = time.time()
    buyer_result = run_buyer_search(company, slug)
    buyer_elapsed = time.time() - t0
    print(f"\n  Buyer search complete in {buyer_elapsed:.1f}s")
    print(f"  Buyers:    {buyer_result['concentric']['scanned']:,} scanned, "
          f"{buyer_result['concentric']['targeted']:,} targeted, "
          f"{buyer_result['concentric']['previewed']} previewed, "
          f"{len(buyer_result.get('segments', []))} segments")

    # Run investor search (unchanged)
    print(f"\n[Phase 5] Running investor search...")
    t1 = time.time()
    investor_result = run_investor_search(company)
    inv_elapsed = time.time() - t1
    print(f"\n  Investor search complete in {inv_elapsed:.1f}s")
    print(f"  Investors: {investor_result['concentric']['scanned']:,} scanned, "
          f"{investor_result['concentric']['targeted']:,} targeted, "
          f"{investor_result['concentric']['previewed']} previewed")

    # Generate fit notes for flat buyer list + investors
    print(f"\n[Phase 6] Generating fit notes...")
    client = anthropic.Anthropic()
    buyers_flat, investors = generate_fit_notes(
        client, company,
        buyer_result["contacts"],
        investor_result["contacts"],
    )

    # Build fit_note map from flat list to propagate back into segments
    fit_map = {}
    for c in buyers_flat:
        key = (c.get("display_name", ""), c.get("organization_name", ""))
        if c.get("fit_note"):
            fit_map[key] = c["fit_note"]

    # Strip internal fields before output
    def clean_contact(c: dict) -> dict:
        base = {
            "first_name": c["first_name"],
            "last_name": c["last_name"],
            "display_name": c["display_name"],
            "initials": c["initials"],
            "title": c["title"],
            "organization_name": c["organization_name"],
            "city": c.get("city", ""),
            "state": c.get("state", ""),
            "country": c.get("country", ""),
            "fit_note": c.get("fit_note", ""),
        }
        # Preserve type/reason for buyer segment contacts
        if c.get("type"):
            base["type"] = c["type"]
        if c.get("reason"):
            base["reason"] = c["reason"]
        return base

    # Build cleaned segments with fit notes propagated
    cleaned_segments = []
    for seg in buyer_result.get("segments", []):
        cleaned_contacts = []
        for c in seg["contacts"]:
            key = (c.get("display_name", ""), c.get("organization_name", ""))
            if key in fit_map and not c.get("fit_note"):
                c["fit_note"] = fit_map[key]
            cleaned_contacts.append(clean_contact(c))
        cleaned_segments.append({
            "segment_name": seg["segment_name"],
            "contacts": cleaned_contacts,
        })

    output = {
        "buyers": {
            "concentric": buyer_result["concentric"],
            "segments": cleaned_segments,
            "contacts": [clean_contact(c) for c in buyers_flat],
        },
        "investors": {
            "concentric": investor_result["concentric"],
            "contacts": [clean_contact(c) for c in investors],
        },
        "hubspot_field_mapping": build_hubspot_mapping(
            comp.get("name", ""), comp.get("sector", ""), comp.get("stage", "")
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": SONNET_MODEL,
        "credits_consumed": 0,
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    n_named = sum(1 for s in cleaned_segments for c in s["contacts"] if c.get("type") == "named_target")
    n_disc = sum(1 for s in cleaned_segments for c in s["contacts"] if c.get("type") == "discovered")
    print(f"\n{'=' * 60}")
    print(f"STEP 2b COMPLETE")
    print(f"  Output: {output_path}")
    print(f"  Buyer segments:    {len(cleaned_segments)}")
    print(f"  Named targets:     {n_named}")
    print(f"  Discovered:        {n_disc}")
    print(f"  Investor contacts: {len(output['investors']['contacts'])}")
    print(f"  Credits consumed:  0")
    print(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step2b_apollo_contacts.py <company-slug>")
        print("Example: python3 step2b_apollo_contacts.py fuse-power")
        sys.exit(1)

    slug = sys.argv[1]
    output = run_step2b(slug)
    print(f"\nDone. Output at: {output}")
