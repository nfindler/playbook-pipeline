#!/usr/bin/env python3
"""
Step 6: Strategic Synthesis
Model: Opus (highest reasoning capability)
Input: ALL JSON from Steps 1-5
Output: data/[slug]/step6-synthesis.json
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

OPUS_MODEL = "claude-opus-4-20250514"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")

# Load the system prompt from the reference file
SYNTHESIS_PROMPT_PATH = SKILL_ROOT / "references" / "synthesis-prompt.md"


def load_system_prompt() -> str:
    with open(SYNTHESIS_PROMPT_PATH) as f:
        content = f.read()
    # Extract the system prompt between ``` markers
    match = re.search(r'```\n(.*?)```', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content


def load_all_steps(slug: str) -> dict:
    data_dir = SKILL_ROOT / "data" / slug
    steps = {}
    for name, filename in [
        ("step1_company", "step1-company.json"),
        ("step2_investors", "step2-investors.json"),
        ("step3_grants", "step3-grants.json"),
        ("step4_market", "step4-market.json"),
        ("step5_experts", "step5-experts.json"),
    ]:
        path = data_dir / filename
        if path.exists():
            with open(path) as f:
                steps[name] = json.load(f)
        else:
            print(f"  WARNING: {path} not found")
            steps[name] = None
    return steps


def compact_step_data(steps: dict) -> dict:
    """Compact step data to stay within token budget. Remove raw/verbose fields."""
    compact = {}

    # Step 1: Company (keep all, it's the foundation)
    if steps.get("step1_company"):
        compact["company"] = steps["step1_company"]

    # Step 2: Investors (keep top 15, trim verbose fields)
    if steps.get("step2_investors"):
        inv = steps["step2_investors"]
        compact["investors"] = {
            "pipeline_stats": inv.get("pipeline_stats", {}),
            "action_summary": inv.get("action_summary", {}),
            "top_matches": [{
                "name": i["name"], "fund": i["fund"], "score": i["score"],
                "action_level": i["action_level"], "check_size": i["check_size"],
                "investor_type": i["investor_type"],
                "thesis_summary": i.get("thesis_summary", ""),
                "intro_path": i.get("intro_path", {}),
                "approach": i.get("approach", ""),
                "insights": i.get("insights", []),
                "confidence_notes": i.get("confidence_notes", ""),
            } for i in inv.get("investors", [])[:15]],
        }

    # Step 3: Grants
    if steps.get("step3_grants"):
        g = steps["step3_grants"]
        compact["grants"] = {
            "pipeline_stats": g.get("pipeline_stats", {}),
            "direct_grants": g.get("direct_grants", []),
            "grants_as_bd": g.get("grants_as_bd", []),
        }

    # Step 4: Market (trim raw research data)
    if steps.get("step4_market"):
        m = steps["step4_market"]
        compact["market"] = {k: v for k, v in m.items()
                             if k not in ("raw_research",)}

    # Step 5: Experts
    if steps.get("step5_experts"):
        compact["experts"] = steps["step5_experts"]

    return compact


def run_step6(slug: str) -> Path:
    data_dir = SKILL_ROOT / "data" / slug
    output_path = data_dir / "step6-synthesis.json"

    system_prompt = load_system_prompt()
    steps = load_all_steps(slug)

    company_name = steps.get("step1_company", {}).get("company", {}).get("name", slug)
    print(f"{'='*60}")
    print(f"STEP 6: Strategic Synthesis (Opus)")
    print(f"Company: {company_name}")
    print(f"{'='*60}")

    compact = compact_step_data(steps)

    user_msg = f"""Generate the strategic synthesis for {company_name}.

Here is ALL structured data from the research pipeline (Steps 1-5):

{json.dumps(compact, indent=1)}

Generate the complete synthesis JSON with these sections:
- opportunity_headline: A punchy, max 15-word headline about the MARKET opportunity (not company claims). Focus on market size, CAGR, or demand driver. Example: "V2G market exploding at 26.5% CAGR to $66B by 2035". No source citations.
- opportunity_subheadline: Max 200 characters. 2-3 short sentences about regulatory tailwinds, demand drivers, or policy momentum. No citations.
- tam_short: Max 60 characters. Just the dollar figure and growth rate. Example: "$6-8B today, $50-66B by 2035". No parenthetical explanations.
- creative_opportunities (3-5)
- key_questions (8-15)
- competitive_position
- strategy_pillars (4: Capital, Grants, Sales/Partnerships, Marketing/Signals)
- alerts (1-3)
- intake_answers: Pre-fill answers to these 14 intake questions based ONLY on verified web research data. Use the question number as the key (e.g. "1", "2", etc.). Leave empty string "" if you cannot answer from the research data. Do NOT guess or fabricate answers. For Q1-Q2 and Q14, always leave as empty string "".
  Q1: "What about this playbook felt accurate?"
  Q2: "What about this playbook felt inaccurate?"
  Q3: "Tell us about your company and team."
  Q4: "What are your top 1-3 objectives right now?"
  Q5: "What are your biggest constraints today?"
  Q6: "How do you create demand today? Sales teams? Founder-led sales?"
  Q7: "What is working? What is not?"
  Q8: "Any signed pilots, POs, or LOIs?"
  Q9: "Who are your customer segments?"
  Q10: "Tell us about your fundraising."
  Q11: "What's your non-dilutive/grants situation?"
  Q12: "Any market entry plans for new markets?"
  Q13: "Any notes on First Nations/Indigenous opportunities?"
  Q14: "Which of our services are of interest to you?"

Follow every rule in your system prompt. Output ONLY valid JSON."""

    print(f"  Input size: ~{len(user_msg)//1000}K chars")
    print(f"  Calling Opus for strategic synthesis (streaming)...")
    t0 = time.time()

    client = anthropic.Anthropic()
    # Use streaming for Opus (required for long operations)
    raw_chunks = []
    input_tokens = 0
    output_tokens = 0
    with client.messages.stream(
        model=OPUS_MODEL,
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for event in stream:
            pass
        response = stream.get_final_message()

    raw = response.content[0].text.strip()
    elapsed = time.time() - t0
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    print(f"  Opus responded in {elapsed:.1f}s ({input_tokens} in / {output_tokens} out)")
    cost_in = input_tokens * 15 / 1_000_000
    cost_out = output_tokens * 75 / 1_000_000
    print(f"  Estimated cost: ${cost_in + cost_out:.2f} (${cost_in:.2f} in + ${cost_out:.2f} out)")

    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        depth = 0
        start = raw.index('{')
        for i in range(start, len(raw)):
            if raw[i] == '{': depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(raw[start:i+1])
                        break
                    except:
                        continue
        else:
            print(f"  [ERROR] Failed to parse Opus JSON")
            result = {"error": "parse_failed", "raw": raw[:3000]}

    output = {
        "company": company_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": OPUS_MODEL,
        "token_usage": {
            "input": input_tokens,
            "output": output_tokens,
        },
        **result,
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Summary
    opps = result.get("creative_opportunities", [])
    qs = result.get("key_questions", [])
    alerts = result.get("alerts", [])
    print(f"\n{'='*60}")
    print(f"STEP 6 COMPLETE")
    print(f"  Creative opportunities: {len(opps)}")
    for o in opps:
        print(f"    - {o.get('name','?')} (confidence: {o.get('confidence','?')})")
    print(f"  Key questions: {len(qs)}")
    print(f"  Alerts: {len(alerts)}")
    for a in alerts:
        print(f"    - {a if isinstance(a, str) else a.get('headline', str(a)[:80])}")
    print(f"{'='*60}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 step6_synthesis.py <slug>")
        sys.exit(1)
    run_step6(sys.argv[1])
