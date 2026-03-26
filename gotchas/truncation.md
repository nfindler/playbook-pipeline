# Gotcha: Truncation on Large JSON Assembly

## The Problem

When you ask a model to take structured JSON data (67K+ characters) and emit it as formatted HTML, the model consistently truncates the output. Sections get cut off, investor cards stop at #7 of 10, detail fields get shortened or omitted. This is a fundamental context window / output length limitation, not a bug you can prompt around.

## Where This Was Discovered

RADAR Step 4. The original pipeline asked Claude to take the assembled research JSON and generate the final HTML page. It worked for small companies with limited data. It broke consistently for companies with rich data (many investors, detailed market analysis, extensive grant opportunities).

The failure mode: the model would start generating HTML correctly, then begin truncating detail fields, then skip entire sections, then stop mid-tag. The output looked fine at the beginning and fell apart toward the end.

## The Fix

**Step 7 of the playbook pipeline MUST be Python template injection, not model generation.**

```python
# CORRECT: Python reads JSON, injects into HTML template
import json

with open('data/step6-synthesis.json') as f:
    data = json.load(f)

with open('templates/playbook-template.html') as f:
    template = f.read()

# Inject each data section into corresponding template slot
html = template
html = html.replace('{{COMPANY_NAME}}', data['company']['name'])
html = html.replace('{{DISCOVERY_COUNT}}', str(calculate_discovery_count(data)))
# ... for every data slot in the template

with open(f'output/{slug}.html', 'w') as f:
    f.write(html)
```

```python
# WRONG: Asking the model to generate HTML from JSON
response = anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{
        "role": "user",
        "content": f"Take this JSON and generate the full HTML playbook page:\n{json.dumps(data)}"
    }]
)
# This WILL truncate for any substantial dataset
```

## Why This Works

- Python has no output length limit
- Template injection is deterministic (no hallucination risk)
- The HTML template is the v7 design we built and tested
- Data slots are clearly defined, every field has a home
- The model's job ends at Step 6 (strategic reasoning), which is what it's good at

## Template Architecture

The HTML template uses data injection markers like `{{INVESTOR_CARDS}}`, `{{OPPORTUNITY_CARDS}}`, `{{GRANT_ANALYSIS}}`, etc. The Python script builds each section's HTML from the JSON data and replaces the markers.

For repeating elements (investor cards, opportunity cards), the script uses sub-templates:
```python
investor_html = ""
for inv in data['investors']:
    card = INVESTOR_CARD_TEMPLATE
    card = card.replace('{{INV_NAME}}', inv['name'])
    card = card.replace('{{INV_SCORE}}', str(inv['score']))
    # ... etc
    investor_html += card
html = html.replace('{{INVESTOR_CARDS}}', investor_html)
```

## Related Patterns

This is the same architecture as:
- RADAR Step 4 (where this lesson was learned)
- Any pipeline that assembles large structured outputs
- The general principle: models reason, code assembles
