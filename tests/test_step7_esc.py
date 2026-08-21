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
    ("Cheque size $1M – $5M typical", "Cheque size $1M to $5M typical"),  # spaced form
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


def main():
    failures = check_trl_none()
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
