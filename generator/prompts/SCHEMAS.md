# Playbook generator prompt schemas (CC-dispatch contract)

This is the manifest for every Anthropic API call site in the v1 playbook
generator. CC-D's `dispatch_to_cc()` replaces the Anthropic client; the
contract here is what each site sends + what shape it expects back.

Live as of 2026-05-23 (pivot day). The Python contract module is
`generator/prompts/cc_dispatch_contract.py`; the JS twin is
`cc_dispatch_contract.js`. Both expose `wrap_prompt_for_cc(msg, schema)`
and `parse_cc_result(text, schema)`.

## Marker contract

Every CC-dispatched prompt asks the sub-CC to enclose its answer between:

```
===CC_RESULT_START===
<payload>
===CC_RESULT_END===
```

The parser:

1. Strips text before/after the markers.
2. Removes any stray ` ```json ` fences inside the block.
3. For `text` schemas, returns the block as-is.
4. For `object` / `array` schemas, `json.loads`; on failure, brace-balance
   extracts the first valid value of the right top-level type.
5. Validates top-level type matches the schema; raises
   `CCResultParseError` if not.

## Per-prompt-site catalog

| Schema id | File | Top level | Web search | max_tokens | Failure modes seen in legacy API path |
|---|---|---|---|---|---|
| `step1_web_search`           | step1_company_research.py:217   | text   | YES | 8192  | Rate-limit on web_search tool, returned partial dossier |
| `step1_haiku_extraction`     | step1_company_research.py:410   | object | no  | 16000 | Truncation on large input; "step1 has no skeleton fallback" : full failure |
| `step2_investor_batch`       | step2_investor_matching.py:695  | array  | no  | 16000 | Markdown fences in output; salvage parser exists |
| `step2b_named_targets`       | step2b_apollo_contacts.py:369   | object | no  | 4000  | Returns `{named_targets:[], broad_segments:[]}` on error |
| `step2b_fit_notes`           | step2b_apollo_contacts.py:888   | array  | no  | 8000  | Truncated arrays; legacy salvages partial |
| `step3_grants_web_search`    | step3_grant_scanning.py:636     | text   | YES | 8192  | Same web_search rate-limit class |
| `step3_grants_eligibility`   | step3_grant_scanning.py:738     | array  | no  | 16000 | Markdown fences + bracket extract fallback |
| `step3_grants_as_bd_search`  | step3_grant_scanning.py:807     | text   | YES | 6000  | : |
| `step3_grants_as_bd_extract` | step3_grant_scanning.py:825     | array  | no  | 4000  | : |
| `step4_market_web_research`  | step4_market_intelligence.py:98 | text   | YES | 12000 | 15 web_searches per call; biggest spend per playbook |
| `step4_market_analysis`      | step4_market_intelligence.py:220| object | no  | 16000 | Brace-balance fallback on truncated JSON |
| `step5_expert_rationale`     | step5_expert_matching.py:168    | object | no  | 8000  | Brace-balance fallback on truncated JSON |
| `step6_synthesis`            | step6_synthesis.py:168          | object | no  | 20000 | Opus stream; brace-balance fallback; cost-sensitive |
| `proxy_inline_edit`          | playbook-editor-proxy.js:310    | object | no  | 8192  | Editor proxy; per-section schema varies |

## Web-search calls (4 of 14)

CC dispatch cannot mirror Anthropic's server-side `web_search_20250305`
tool. The four `needs_web_search: true` sites have three options:

1. **Sub-CC uses its own WebSearch + WebFetch tools.** Cleanest. The
   dispatch wrapper must spawn a sub-CC that has those tools enabled
   (the default Agent profile already does). The marker contract is the
   same; the sub-CC just emits its dossier between markers after using
   the tools.
2. **Pre-fetch externally and hand the content in.** For Carbonyx-class
   demos, a thin shell wrapper around `curl` / `playwright` + the relevant
   query list, fed into the user_msg, also works. More brittle.
3. **Cache and reuse.** Web research dossiers for a given company /
   sector / quarter rarely change inside a day. Hash the input and reuse
   the cached dossier if one exists. The legacy code did not do this.

For the Nick demo: option 1. CC-D's `dispatch_to_cc()` should not strip
the sub-CC's tool affordances.

## Wiring pattern (per site)

```python
# Was:
response = client.messages.create(
    model=HAIKU_MODEL,
    max_tokens=8192,
    system=system_prompt,
    messages=[{"role": "user", "content": user_msg}],
)
raw = response.content[0].text
data = json.loads(raw)  # plus the legacy salvage tangle

# Becomes:
from generator.prompts.cc_dispatch_contract import wrap_prompt_for_cc, parse_cc_result
wrapped = wrap_prompt_for_cc(user_msg, "step1_haiku_extraction")
raw = dispatch_to_cc(prompt=wrapped, system=system_prompt, model="opus", max_tokens=16000)
data = parse_cc_result(raw, "step1_haiku_extraction")
```

The system prompt does not need wrapping : only the user message carries
the marker contract.

## Failure-mode handling

`parse_cc_result` raises `CCResultParseError(reason, raw_excerpt, schema_name)`
on:

* `missing_start_marker` / `missing_end_marker` : sub-CC ignored the contract
* `malformed_json` : markers present, payload between them isn't valid JSON
  even after brace-balance fallback
* `wrong_top_level:expected_object` / `expected_array` : sub-CC emitted the
  wrong root shape

Caller decides whether to retry, fall through to a skeleton, or surface
the error. Recommended pattern per step:

```python
try:
    data = parse_cc_result(raw, "step1_haiku_extraction")
except CCResultParseError as e:
    log.warning("step1 cc parse failed: %s; raw=%r", e.reason, e.raw_excerpt)
    return {"error": e.reason, "raw_output": e.raw_excerpt}
```

## Token-budget notes

CC dispatch turn ceiling for Opus 4.7 is ~32K output tokens per turn,
well above any single legacy `max_tokens` setting. Increases in this
table (step1_haiku_extraction 8192 -> 16000; step2b_fit_notes 6000 ->
8000; step6_synthesis 16000 -> 20000) reflect known truncation incidents
in the legacy API path : CC dispatch can absorb them safely.

Input context ceiling on Opus 4.7 is 1M tokens; even the
step4_market_analysis call (~50K user_msg) is comfortably within budget.

## Adding a new prompt site

1. Add an entry to `PROMPT_SCHEMAS` in **both** Python and JS modules.
2. Add a row to the table above.
3. At the call site, replace `client.messages.create(...)` with
   `dispatch_to_cc(wrap_prompt_for_cc(user_msg, "<id>"), ...)` and
   `parse_cc_result(raw, "<id>")`.
4. Run the contract self-test: `python3 -m generator.prompts.cc_dispatch_contract`
   and `node generator/prompts/cc_dispatch_contract.js`.
