#!/usr/bin/env python3
"""
Step 5: Expert Matching
Model: Sonnet (matching + rationale generation)
Input: data/[slug]/step1-company.json + experts.json (28 contacts)
Output: data/[slug]/step5-experts.json
"""

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


import json, sys, re, time
from datetime import datetime, timezone
from pathlib import Path
import anthropic

SONNET_MODEL = "claude-sonnet-4-6"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")
EXPERTS_PATH = Path("/home/openclaw/radar-platform/data/experts.json")

# ClimateDoor Growth Pod team (not in the experts DB)
GROWTH_POD = [
    {"name": "Nick Findler", "role": "CEO & Growth Lead", "focus": "Capital strategy, investor relationships, strategic direction", "assignment_trigger": "All clients"},
    {"name": "Sam", "role": "Growth Pod - BD", "focus": "Business development, partnerships, corporate sales", "assignment_trigger": "Sales/Partnerships service need"},
    {"name": "Ash", "role": "Growth Pod - Marketing", "focus": "Marketing strategy, brand positioning, go-to-market", "assignment_trigger": "Marketing service need"},
    {"name": "Sophie Kennedy", "role": "Growth Pod - Grants", "focus": "Grant strategy, application support, funding agency relationships", "assignment_trigger": "Grants service need"},
    {"name": "Tiff", "role": "Growth Pod - Indigenous", "focus": "Indigenous community relationships, ICP4 partnerships, reconciliation", "assignment_trigger": "Indigenous opportunity identified"},
]


def load_experts() -> list[dict]:
    with open(EXPERTS_PATH) as f:
        data = json.load(f)
    return data["experts"]


def match_experts_to_company(experts: list[dict], company: dict) -> list[dict]:
    """Score each expert against the company profile using keyword matching."""
    comp = company.get("company", {})
    sector = (comp.get("sector", "") + " " + comp.get("sub_sector", "")).lower()
    geo = comp.get("geography", {}).get("hq", "").lower()
    product = company.get("product", {}).get("description", "").lower()
    buyers = " ".join(company.get("market", {}).get("target_buyers", [])).lower()

    # Keywords to match
    sector_kw = ["circular", "textile", "fashion", "sustainable", "recycl", "waste", "medical",
                 "health", "consumer", "manufacturing", "clean"]
    geo_kw = ["canada", "quebec", "europe", "eu"]
    service_kw = ["capital", "grants", "partnerships", "marketing", "eu lcba", "market entry"]

    scored = []
    for exp in experts:
        score = 0
        reasons = []

        # Sector match
        exp_sector = (exp.get("sector_expertise", "") or "").lower()
        exp_notes = (exp.get("talent_notes", "") or "").lower()
        for kw in sector_kw:
            if kw in exp_sector or kw in exp_notes:
                score += 10
                reasons.append(f"sector:{kw}")

        # Geography match
        exp_geo = (exp.get("geography_focus", "") or "").lower()
        for kw in geo_kw:
            if kw in exp_geo:
                score += 8
                reasons.append(f"geo:{kw}")

        # Service match
        exp_service = (exp.get("service_interest", "") or "").lower()
        for kw in service_kw:
            if kw in exp_service:
                score += 5
                reasons.append(f"service:{kw}")

        # Agreement signed bonus
        if exp.get("agreement_signed") == "Yes":
            score += 10

        # Seniority bonus
        if exp.get("seniority") == "Executive":
            score += 5
        elif exp.get("seniority") == "Senior":
            score += 3

        scored.append({
            "expert": exp,
            "score": score,
            "match_reasons": reasons,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def run_sonnet_rationale(top_experts: list[dict], company: dict, growth_pod: list[dict]) -> dict:
    """Generate rationales for matched experts and Growth Pod assignments."""
    client = anthropic.Anthropic()

    comp = company.get("company", {})
    summary = {
        "name": comp.get("name", ""),
        "description": comp.get("description", ""),
        "sector": comp.get("sector", ""),
        "sub_sector": comp.get("sub_sector", ""),
        "geography": comp.get("geography", {}),
        "product": company.get("product", {}).get("description", ""),
        "target_buyers": company.get("market", {}).get("target_buyers", []),
        "data_gaps": company.get("data_gaps", [])[:5],
    }

    expert_summaries = []
    for e in top_experts:
        exp = e["expert"]
        expert_summaries.append({
            "name": exp["name"],
            "location": exp["location"],
            "expert_type": exp["expert_type"],
            "sector_expertise": exp.get("sector_expertise", ""),
            "geography_focus": exp.get("geography_focus", ""),
            "service_interest": exp.get("service_interest", ""),
            "seniority": exp.get("seniority", ""),
            "agreement_signed": exp.get("agreement_signed", ""),
            "talent_notes": (exp.get("talent_notes", "") or "")[:400],
            "match_score": e["score"],
            "match_reasons": e["match_reasons"],
        })

    user_msg = f"""Match experts and Growth Pod team members to this company.

COMPANY: {json.dumps(summary, indent=2)}

TOP EXPERT MATCHES (from 28 in database, pre-scored):
{json.dumps(expert_summaries, indent=2)}

GROWTH POD TEAM:
{json.dumps(growth_pod, indent=2)}

Output a JSON object with two arrays:

1. "expert_matches": For each expert worth including (score >= 15 or strong rationale), output:
   - name, title (from their talent_notes or expert_type), location
   - agreement_status: "Yes" or "No"
   - match_score: number
   - why_this_company: 2-3 sentences (based ONLY on facts from their talent_notes and the company profile)
   - specific_value: what exactly they would do for this company
   - deployment_recommendation: when/how to engage them
   - linkedin: from their record

2. "growth_pod_assignments": For each CD team member, output:
   - name, role, assignment_rationale: 1-2 sentences

Output ONLY the JSON object."""

    print(f"  Calling Sonnet for expert rationales...")
    t0 = time.time()
    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8000,
        system="You are a talent matching analyst for ClimateDoor. Match experts to companies based on actual expertise, not assumptions. Bios come from the database, NEVER generated. Output valid JSON only.",
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
            if raw[i] == '{': depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    try: return json.loads(raw[start:i+1])
                    except: continue
        return {"error": "parse_failed"}


def run_step5(slug: str) -> Path:
    data_dir = SKILL_ROOT / "data" / slug
    step1_path = data_dir / "step1-company.json"
    output_path = data_dir / "step5-experts.json"

    with open(step1_path) as f:
        company = json.load(f)

    comp = company.get("company", {})
    print(f"={'='*59}")
    print(f"STEP 5: Expert Matching")
    print(f"Company: {comp.get('name')}")
    print(f"{'='*60}")

    experts = load_experts()
    print(f"  Loaded {len(experts)} experts from database")

    scored = match_experts_to_company(experts, company)
    top = scored[:10]
    print(f"  Top scores: {[(s['expert']['name'], s['score']) for s in top[:5]]}")

    result = run_sonnet_rationale(top, company, GROWTH_POD)

    output = {
        "company": comp.get("name", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": SONNET_MODEL,
        "total_experts_in_db": len(experts),
        "experts_evaluated": len(top),
        **result,
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    em = result.get("expert_matches", [])
    gp = result.get("growth_pod_assignments", [])
    print(f"\n{'='*60}")
    print(f"STEP 5 COMPLETE")
    print(f"  Expert matches: {len(em)}")
    print(f"  Growth Pod assignments: {len(gp)}")
    for e in em[:3]:
        print(f"    - {e.get('name','')} | {e.get('specific_value','')[:60]}")
    print(f"{'='*60}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step5_expert_matching.py <slug>")
        sys.exit(1)
    run_step5(sys.argv[1])
