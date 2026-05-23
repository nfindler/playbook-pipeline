"""
CC-dispatch contract (pivot from Anthropic API to CC subscription).

CC-D builds the transport: dispatch_to_cc(prompt, model=None, max_tokens=None) -> str.
This module owns the *prompt + parse* contract on top of that transport.

Wire-up pattern at each existing Anthropic call site:

    from generator.prompts.cc_dispatch_contract import (
        wrap_prompt_for_cc, parse_cc_result,
    )
    wrapped = wrap_prompt_for_cc(user_msg, "step5_expert_rationale")
    raw = dispatch_to_cc(prompt=wrapped, model="opus", max_tokens=8000)
    data = parse_cc_result(raw, "step5_expert_rationale")

Markers chosen to be unambiguous (no chance of collision with normal prose
or with markdown code fences):

    ===CC_RESULT_START===
    { ...JSON... }
    ===CC_RESULT_END===

Sub-CCs sometimes wrap JSON in ```json fences anyway; the parser strips
fences inside the marker block before json.loads().

Failure modes handled:
  * Missing start or end marker -> CCResultParseError("missing_markers")
  * Multiple marker pairs       -> use the FIRST pair, log a warning
  * Fenced JSON inside markers  -> strip the fences
  * Trailing prose inside block -> attempt brace-balance fallback
  * Top-level type mismatch     -> CCResultParseError("wrong_top_level")

Schemas are *contracts*, not full JSON-schema. They name the prompt site,
declare the expected top-level type (object vs array), and carry an
INSTRUCTION_SUFFIX that gets appended to the user message so the sub-CC
knows what shape to produce. The full nested shape stays inline in the
original step script where it already lives; this module only owns the
envelope.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


MARKER_START = "===CC_RESULT_START==="
MARKER_END = "===CC_RESULT_END==="


class CCResultParseError(Exception):
    """Raised when the marker contract is violated or JSON cannot be parsed."""

    def __init__(self, reason: str, raw_excerpt: str = "", schema_name: str = ""):
        self.reason = reason
        self.raw_excerpt = raw_excerpt[:2000]
        self.schema_name = schema_name
        super().__init__(f"{reason} (schema={schema_name})")


# ---------------------------------------------------------------------------
# Per-prompt-site contract table.
#
# `top_level`: "object" or "array"
# `notes`: model tier hint (Haiku-class for extractive, Sonnet-class for
#          analysis, Opus-class for the synthesis pass), and any failure
#          modes that need special handling.
# `needs_web_search`: True for the 4 sites that currently use Anthropic's
#          server-side web_search tool. CC dispatch cannot mirror that tool
#          server-side; the sub-CC must use its own WebSearch / WebFetch.
# `max_tokens_suggested`: matches the current API setting; CC-D can use this
#          as a per-call ceiling hint for dispatch_to_cc.
# ---------------------------------------------------------------------------

PROMPT_SCHEMAS: dict[str, dict[str, Any]] = {
    "step1_web_search": {
        "top_level": "text",
        "needs_web_search": True,
        "max_tokens_suggested": 8192,
        "notes": (
            "Returns a free-form research dossier as plain text. NOT JSON; "
            "parse_cc_result is bypassed for this site. Caller passes the "
            "text into step1_haiku_extraction as web_search_content."
        ),
    },
    "step1_haiku_extraction": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 16000,   # raised from 8192; large schema
        "notes": (
            "Massive nested company schema (company, product, funding, team, "
            "market, traction, signals, data_gaps, generation_metadata). "
            "Input is ~150K chars; needs Opus or Sonnet, not Haiku, when run "
            "through CC dispatch (Haiku may truncate)."
        ),
    },
    "step2_investor_batch": {
        "top_level": "array",
        "needs_web_search": False,
        "max_tokens_suggested": 16000,
        "notes": (
            "Each element: {db_id, thesis_summary, approach, insights[], "
            "intro_path:{type,detail,source}, confidence_notes}. db_id must "
            "match the input ID exactly. Batch size ~10-20 candidates."
        ),
    },
    "step2b_named_targets": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 4000,
        "notes": (
            "{named_targets[], broad_segments[]}. Named targets must be "
            "explicitly mentioned in the input intelligence; do not invent."
        ),
    },
    "step2b_fit_notes": {
        "top_level": "array",
        "needs_web_search": False,
        "max_tokens_suggested": 8000,   # raised from 6000; truncation observed
        "notes": (
            "Each element: {idx, fit_note}. idx is the contact index "
            "(B0..Bn for buyers, I0..In for investors). Truncation is a "
            "known failure mode; the legacy parser salvages partial arrays."
        ),
    },
    "step3_grants_web_search": {
        "top_level": "text",
        "needs_web_search": True,
        "max_tokens_suggested": 8192,
        "notes": "Plain-text grant program research dossier.",
    },
    "step3_grants_eligibility": {
        "top_level": "array",
        "needs_web_search": False,
        "max_tokens_suggested": 16000,
        "notes": (
            "Each element is a grant program (program_name, agency, "
            "program_url, source, amount_range, funding_type, "
            "type_of_funding, intake_status, next_deadline, "
            "application_start_date, application_end_date, eligibility_fit, "
            "eligibility_details, strategic_value, effort_estimate, "
            "confidence, confidence_reasoning, notion_page_id, "
            "notion_page_url)."
        ),
    },
    "step3_grants_as_bd_search": {
        "top_level": "text",
        "needs_web_search": True,
        "max_tokens_suggested": 6000,
        "notes": "Plain-text grants-as-BD analysis dossier.",
    },
    "step3_grants_as_bd_extract": {
        "top_level": "array",
        "needs_web_search": False,
        "max_tokens_suggested": 4000,
        "notes": (
            "Each element: {type='grants_as_bd', customer_type, "
            "grant_program, program_url, customer_eligibility, "
            "how_it_works, estimated_value, confidence, "
            "confidence_reasoning}."
        ),
    },
    "step4_market_web_research": {
        "top_level": "text",
        "needs_web_search": True,
        "max_tokens_suggested": 12000,
        "notes": (
            "Plain-text market research dossier covering buyers, "
            "competitors, market signals, conferences, indigenous angles, "
            "market sizing."
        ),
    },
    "step4_market_analysis": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 16000,
        "notes": (
            "{buyer_segments[], market_signals[], competitive_landscape[], "
            "conference_targets[], indigenous_opportunities[], "
            "sector_temperature{}, market_sizing{}}. Conference dates must "
            "be after `today`."
        ),
    },
    "step5_expert_rationale": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 8000,
        "notes": (
            "{expert_matches[], growth_pod_assignments[]}. Each match "
            "carries name, title, location, agreement_status, match_score, "
            "why_this_company, specific_value, deployment_recommendation, "
            "linkedin. Bios must come from talent_notes, never invented."
        ),
    },
    "step6_synthesis": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 20000,   # raised from 16000; long output
        "notes": (
            "{opportunity_headline, opportunity_subheadline, tam_short, "
            "creative_opportunities[3-5], key_questions[8-15], "
            "competitive_position, strategy_pillars{Capital, Grants, "
            "Sales/Partnerships, Marketing/Signals}, alerts[1-3], "
            "intake_answers{1..14}}. Opus-tier reasoning required."
        ),
    },
    "proxy_inline_edit": {
        "top_level": "object",
        "needs_web_search": False,
        "max_tokens_suggested": 8192,
        "notes": (
            "Editor-proxy ad-hoc prompt (playbook-editor-proxy.js). Caller "
            "decides expected shape per section; default object."
        ),
    },
}


# ---------------------------------------------------------------------------
# Prompt wrapping
# ---------------------------------------------------------------------------

def wrap_prompt_for_cc(user_msg: str, schema_name: str) -> str:
    """Append the CC marker + schema contract to a user message.

    Idempotent: if `user_msg` already carries the markers, returns it
    unchanged. Raises KeyError if `schema_name` is not registered.
    """
    if schema_name not in PROMPT_SCHEMAS:
        raise KeyError(f"unknown CC prompt schema: {schema_name!r}")
    if MARKER_START in user_msg and MARKER_END in user_msg:
        return user_msg

    schema = PROMPT_SCHEMAS[schema_name]
    top = schema["top_level"]

    if top == "text":
        instruction = (
            "\n\n---\n"
            "OUTPUT CONTRACT\n"
            f"Respond between the markers below. Plain text is fine; no JSON required.\n"
            f"{MARKER_START}\n"
            "<your full research dossier here>\n"
            f"{MARKER_END}\n"
            "Do not emit anything after the closing marker."
        )
    else:
        shape = "JSON object {...}" if top == "object" else "JSON array [...]"
        instruction = (
            "\n\n---\n"
            "OUTPUT CONTRACT\n"
            f"Respond ONLY between the markers below with a single strict {shape} "
            f"matching the schema described above. No markdown fences. No prose "
            f"outside the markers. No comments inside the JSON.\n"
            f"{MARKER_START}\n"
            f"<{shape} here>\n"
            f"{MARKER_END}\n"
            f"Schema id (for caller's reference, do not echo): {schema_name}"
        )
    return user_msg.rstrip() + instruction


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```\w*\n?|\n?```$", re.MULTILINE)


def _extract_marker_block(text: str, schema_name: str) -> str:
    if not isinstance(text, str):
        raise CCResultParseError("not_a_string", str(type(text)), schema_name)
    start = text.find(MARKER_START)
    if start < 0:
        raise CCResultParseError("missing_start_marker", text, schema_name)
    after_start = start + len(MARKER_START)
    end = text.find(MARKER_END, after_start)
    if end < 0:
        raise CCResultParseError("missing_end_marker", text[start:], schema_name)
    block = text[after_start:end].strip()
    # Strip any stray markdown fences inside the marker block.
    block = _FENCE_RE.sub("", block).strip()
    return block


def _brace_balanced_extract(block: str, opener: str, closer: str) -> str | None:
    """Return the first brace-balanced substring starting with `opener`."""
    try:
        start = block.index(opener)
    except ValueError:
        return None
    depth = 0
    for i in range(start, len(block)):
        ch = block[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return block[start : i + 1]
    return None


def parse_cc_result(text: str, schema_name: str) -> Any:
    """Parse a CC dispatch response according to the schema contract.

    For top_level='text': returns the raw text between markers.
    For top_level='object' or 'array': returns the parsed JSON, after
    validating the top-level type matches the schema.
    """
    if schema_name not in PROMPT_SCHEMAS:
        raise KeyError(f"unknown CC prompt schema: {schema_name!r}")
    block = _extract_marker_block(text, schema_name)
    top = PROMPT_SCHEMAS[schema_name]["top_level"]

    if top == "text":
        return block

    # Try a direct JSON parse first.
    try:
        data = json.loads(block)
    except json.JSONDecodeError:
        # Fallback: brace-balance extract the largest valid JSON value.
        opener, closer = ("{", "}") if top == "object" else ("[", "]")
        candidate = _brace_balanced_extract(block, opener, closer)
        if candidate is None:
            raise CCResultParseError("malformed_json", block, schema_name)
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as e:
            raise CCResultParseError(f"malformed_json:{e}", block, schema_name)

    if top == "object" and not isinstance(data, dict):
        raise CCResultParseError("wrong_top_level:expected_object", block, schema_name)
    if top == "array" and not isinstance(data, list):
        raise CCResultParseError("wrong_top_level:expected_array", block, schema_name)
    return data


# ---------------------------------------------------------------------------
# Self-test (run: python3 -m generator.prompts.cc_dispatch_contract)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    failures = 0

    # Wrap roundtrip: object schema
    wrapped = wrap_prompt_for_cc("EXTRACT FOO.", "step5_expert_rationale")
    if MARKER_START not in wrapped or MARKER_END not in wrapped:
        print("FAIL: wrap_prompt_for_cc dropped markers"); failures += 1

    # Parse: clean object
    sample = f"prelude\n{MARKER_START}\n{{\"expert_matches\": [], \"growth_pod_assignments\": []}}\n{MARKER_END}\npostlude"
    d = parse_cc_result(sample, "step5_expert_rationale")
    if not isinstance(d, dict) or "expert_matches" not in d:
        print("FAIL: parse_cc_result object"); failures += 1

    # Parse: array schema
    sample = f"{MARKER_START}\n[{{\"idx\": \"B0\", \"fit_note\": \"x\"}}]\n{MARKER_END}"
    d = parse_cc_result(sample, "step2b_fit_notes")
    if not isinstance(d, list) or d[0]["idx"] != "B0":
        print("FAIL: parse_cc_result array"); failures += 1

    # Parse: stripped markdown fences
    sample = f"{MARKER_START}\n```json\n{{\"a\": 1}}\n```\n{MARKER_END}"
    d = parse_cc_result(sample, "step1_haiku_extraction")
    if d.get("a") != 1:
        print("FAIL: fence-strip parse"); failures += 1

    # Parse: trailing-prose fallback via brace-balance
    sample = f"{MARKER_START}\n{{\"a\": 1}} extra junk\n{MARKER_END}"
    d = parse_cc_result(sample, "step1_haiku_extraction")
    if d.get("a") != 1:
        print("FAIL: trailing-prose fallback"); failures += 1

    # Parse: text schema (free-form dossier)
    sample = f"{MARKER_START}\nsome research findings\nhere\n{MARKER_END}"
    s = parse_cc_result(sample, "step1_web_search")
    if "research findings" not in s:
        print("FAIL: text-schema parse"); failures += 1

    # Parse: missing markers -> error
    try:
        parse_cc_result("no markers here", "step5_expert_rationale")
        print("FAIL: should have raised on missing markers"); failures += 1
    except CCResultParseError:
        pass

    # Parse: wrong top-level type -> error
    sample = f"{MARKER_START}\n[1,2,3]\n{MARKER_END}"
    try:
        parse_cc_result(sample, "step5_expert_rationale")  # expects object
        print("FAIL: should have raised on wrong top level"); failures += 1
    except CCResultParseError:
        pass

    # Wrap idempotency
    wrapped2 = wrap_prompt_for_cc(wrapped, "step5_expert_rationale")
    if wrapped2 != wrapped:
        print("FAIL: wrap_prompt_for_cc not idempotent"); failures += 1

    print(f"selftest: {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_selftest())
