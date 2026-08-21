#!/usr/bin/env python3
"""CLI-4002 item (5): esc() must never emit a dash, never corrupt punctuation, never break a range.

Run standalone (`python3 tests/test_step7_esc.py`) or via `npm test`, which shells out to this file.
Exit 0 all pass, 1 any failure.

WHY THIS FILE EXISTS. esc() replaced an em dash with a bare comma and left the surrounding whitespace
alone, so "USA only - Polysource" rendered as "USA only , Polysource" on 33 client slugs and 8,146
dashes since April. 1,049 of those dashes sat between two numbers, which turned a cheque size or a
date range into what reads like two separate figures: "$1M,$5M" rendered 132 times on the live
estate, alongside "$50M,$500M", "2025,2028" and "TRL range (1,9)".

The brand rule ("never an em dash") is NOT what was wrong and is asserted here too, so a future fix
for the punctuation cannot quietly reintroduce the dash.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("step7", ROOT / "scripts" / "step7_assemble.py")
step7 = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(step7)
except SystemExit:  # the module runs a CLI at import when given argv; ignore that here
    pass
esc = step7.esc

# (input, expected) -- every case is a real shape counted in the source data, not an invented one.
CASES = [
    # Ranges keep their meaning. These are the 1,049 that were changing what a client reads.
    ("Cheque size $1M–$5M typical", "Cheque size $1M to $5M typical"),   # x109 tight
    ("Cheque size $1M – $5M typical", "Cheque size $1M to $5M typical"),  # spaced, BOTH sides marked
    # 55 of the 57 spaced digit-dash-digit occurrences in data/ are grant ranges like these.
    ("$390,000 – $10,000,000 per award", "$390,000 to $10,000,000 per award"),
    ("$1,500 – $500,000 (grants)", "$1,500 to $500,000 (grants)"),
    # ...and the 2 that are NOT ranges: an appositive dash whose left side is a bare date. Treating
    # these as ranges welded two real sentences together on live client pages.
    ("project completion in April 2025 — 5 MWh, 24-hour steam delivery",
     "project completion in April 2025, 5 MWh, 24-hour steam delivery"),
    ("from 486 to 800 ports by spring 2026 — 65% capacity increase",
     "from 486 to 800 ports by spring 2026, 65% capacity increase"),
    ("($100k–$1M)", "($100k to $1M)"),                                    # x44
    ("60–80% conversion", "60 to 80% conversion"),                        # x23
    ("2025–2028 window", "2025 to 2028 window"),                          # x14
    ("Q2–Q3 2026", "Q2 to Q3 2026"),                                      # x12
    ("TRL range (1–9)", "TRL range (1 to 9)"),
    ("12–24 months", "12 to 24 months"),
    # Prose dashes become a comma with exactly one following space, whatever surrounded the dash.
    ("Preferred region is USA only — Polysource is HQ in Langley",
     "Preferred region is USA only, Polysource is HQ in Langley"),
    ("the database—a real one", "the database, a real one"),
    ("a — b — c", "a, b, c"),
    # No digit on the right is prose, not a range, and must not become "to".
    ("Series A–B rounds", "Series A, B rounds"),
    # None and clean input.
    (None, ""),
    ("no dash here", "no dash here"),
    # HTML escaping still happens.
    ("5 > 3 & rising", "5 &gt; 3 &amp; rising"),
]

# The two defects this file exists to prevent, stated as strings that must never appear again.
FORBIDDEN_SUBSTRINGS = [" ,", "—", "–"]


def check_trl_none():
    """CLI-4002 item (5): a null trl must not render the Python sentinel into a client's copy.

    Driven through the REAL build_landscape_tab, not through a copy of the f-string, because the
    defect was precisely that one interpolation on that line skipped the None-safe helper its five
    siblings use. step4-market.json carries "trl": null explicitly, so `.get("trl", "")` returned
    None rather than the default, and the card rendered "TRL None" to the client. Measured live:
    5 cards on sense-and-motion, where that same slot renders a number on 143 cards estate-wide.
    """
    out = []
    fixture = {
        "s4": {
            "competitive_landscape": [
                {"name": "Nulltown Analytics", "trl": None, "funding_known": ""},
                {"name": "Realvalue Systems", "trl": 7, "funding_known": "Series B"},
            ]
        },
        "s6": {},
    }
    html = step7.build_landscape_tab(fixture)
    if "TRL None" in html:
        out.append('build_landscape_tab still renders "TRL None" for a null trl')
    if "TRL unknown" not in html:
        out.append('build_landscape_tab does not render "TRL unknown" for a null trl')
    # Anti-vacuity: a real trl must still render its number, or "never say None" could be satisfied
    # by dropping the field entirely.
    if "TRL 7" not in html:
        out.append('build_landscape_tab lost the real trl value (expected "TRL 7")')
    return out


def check_shape_bugs():
    """CLI-4002 item (5): three producer slots rendered a Python VALUE instead of its content.

    All three are driven through the real builders. Each one is a shape mismatch between what the
    step JSON actually holds and what the renderer assumed, and each was invisible to the estate
    detector because the detector looked for the wrong surface form.
    """
    out = []

    # 1. grant_pathways is a semicolon-joined STRING on 16 slugs. `for gp in <str>` walks CHARACTERS,
    #    so the card rendered "P<br>r<br>a<br>i..." -- a ~500-character column of single letters.
    signals = {"s4": {"indigenous_opportunities": [{
        "community_or_org": "Example Nation", "region": "Prairies", "fit_score": 70,
        "grant_pathways": "PrairiesCan fund; CEC NAPECA grant program",
    }]}, "s6": {}}
    html = step7.build_indigenous_tab(signals)
    if "P<br>r<br>a" in html or ">P<br>" in html:
        out.append("build_indigenous_tab still iterates a grant_pathways STRING one character at a time")
    if "PrairiesCan fund; CEC NAPECA grant program" not in html:
        out.append("build_indigenous_tab lost the grant_pathways text entirely")
    # Anti-vacuity: a real LIST must still render each pathway on its own line.
    signals["s4"]["indigenous_opportunities"][0]["grant_pathways"] = ["Alpha fund", "Beta program"]
    html_list = step7.build_indigenous_tab(signals)
    if "Alpha fund<br>" not in html_list or "Beta program<br>" not in html_list:
        out.append("build_indigenous_tab broke the normal LIST case while fixing the string case")

    # 2. primary_risk is a DICT on 14 of 42 slugs; esc(dict) rendered its Python repr to the client.
    pos = {"s6": {"competitive_position": {
        "intro": "Position summary.",
        "primary_risk": {"risk": "Unproven scale deployment", "mitigant": "Focus on regulated segments"},
    }}, "s4": {}}
    html2 = step7.build_landscape_tab(pos)
    if "{'risk'" in html2 or "&#x27;risk&#x27;" in html2:
        out.append("build_landscape_tab still renders the primary_risk dict as a Python repr")
    if "Unproven scale deployment" not in html2:
        out.append("build_landscape_tab lost the risk text")
    if "Focus on regulated segments" not in html2:
        out.append("build_landscape_tab dropped the mitigant carried inside the dict")
    # The evidence/detail field two of the 14 dicts carry must survive, and the parts must be joined
    # as SENTENCES. Nothing pinned either, and a bare-space join shipped a run-on on princeton-energy.
    pos_ev = {"s6": {"competitive_position": {
        "intro": "x",
        "primary_risk": {"risk": "Capital constraints limit scale", "evidence": "Only one filing found",
                         "mitigant": "Partner for capacity"},
    }}, "s4": {}}
    html_ev = step7.build_landscape_tab(pos_ev)
    if "Only one filing found" not in html_ev:
        out.append("build_landscape_tab dropped the evidence field carried inside the dict")
    if "Capital constraints limit scale Only one filing" in html_ev:
        out.append("build_landscape_tab joins risk and evidence into a run-on with no sentence break")
    if ".. Mitigant" in html_ev or ".. Mitigant" in html2:
        out.append("build_landscape_tab doubles the full stop before Mitigant")

    # Anti-vacuity: a plain STRING primary_risk must still render.
    pos["s6"]["competitive_position"]["primary_risk"] = "A plain sentence risk."
    if "A plain sentence risk." not in step7.build_landscape_tab(pos):
        out.append("build_landscape_tab broke the normal STRING primary_risk case")

    # 3. **markdown** left literal in a heading on 5 slugs: esc() where every sibling slot uses
    #    _parse_detail_bold, which escapes AND converts.
    pos2 = {"s6": {"competitive_position": {
        "intro": "x",
        "defensibility_factors": [{"factor": "**Technological moat**: 2.3M laser points", "evidence": "e"}],
    }}, "s4": {}}
    html3 = step7.build_landscape_tab(pos2)
    if "**Technological moat**" in html3:
        out.append("build_landscape_tab still ships literal **markdown** in comp-factor-title")
    if "<strong>Technological moat</strong>" not in html3:
        out.append("build_landscape_tab did not convert the bold in comp-factor-title")
    return out


def main():
    failures = check_trl_none() + check_shape_bugs()
    for raw, expected in CASES:
        got = esc(raw)
        if got != expected:
            failures.append(f"esc({raw!r})\n     got: {got!r}\nexpected: {expected!r}")

    # Anti-vacuity: assert the forbidden shapes over every case output, so a rewritten CASES table
    # that happens to agree with a broken esc() still fails here.
    for raw, _ in CASES:
        got = esc(raw)
        for bad in FORBIDDEN_SUBSTRINGS:
            if bad in got:
                failures.append(f"esc({raw!r}) -> {got!r} still contains {bad!r}")

    # A guard on the guard: if esc() were replaced by the identity function every case above with a
    # dash would fail, but a case table with no dashes in it would pass vacuously. Require that the
    # table actually exercises the dash paths.
    dashed = sum(1 for raw, _ in CASES if raw and any(d in raw for d in ("–", "—")))
    if dashed < 8:
        failures.append(f"case table only exercises {dashed} dash inputs; it is not testing the fix")

    if failures:
        print("FAIL step7 esc()\n\n" + "\n\n".join(failures))
        return 1
    print(f"ok  step7 esc(): {len(CASES)} cases, {dashed} of them dash-bearing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
