# Gotcha: Picklist Hallucination

## The Problem

When the model is asked to classify or tag data using a predefined set of valid values (a "picklist"), it generates values that sound right but aren't in the list. Examples:

- Picklist has "Solar PV" but model outputs "Solar Photovoltaic"
- Picklist has "Series A" but model outputs "Early Series A"
- Picklist has "British Columbia" but model outputs "BC"
- Picklist has "Circular Economy" but model outputs "Circular Economy & Waste"

These near-misses are worse than random errors because they look correct at a glance.

## Where This Was Discovered

DEBRIEF extraction engines. When classifying call transcripts by ICP tags, the model would generate values that were semantically correct but not in the picklist. This caused downstream matching failures because the ICP cross-matching rules depend on exact picklist values.

## The Fix (Two-Layer Defense)

### Layer 1: Explicit picklist in the system prompt

Don't just say "classify by sector." List every valid value explicitly:

```
Classify the company's sector using ONLY one of these exact values:
- Solar PV
- Wind
- Battery Storage
- Hydrogen
- Carbon Capture
- Circular Economy
- Water Treatment
- Building Efficiency
- EV / Mobility
- Agri-Tech
- Waste Management
- Grid / Transmission
- Other Clean Energy

Do NOT use any value not in this list. Do NOT modify the values.
If no value fits, use "Other Clean Energy" and note the actual sector in the description field.
```

### Layer 2: Post-extraction validation function

After the model returns its classification, validate against the actual picklist:

```python
VALID_SECTORS = [
    "Solar PV", "Wind", "Battery Storage", "Hydrogen",
    "Carbon Capture", "Circular Economy", "Water Treatment",
    "Building Efficiency", "EV / Mobility", "Agri-Tech",
    "Waste Management", "Grid / Transmission", "Other Clean Energy"
]

def validate_extraction(extracted_data):
    """Strip any values that don't match the picklist exactly."""
    
    if extracted_data.get('sector') not in VALID_SECTORS:
        # Try fuzzy match first
        best_match = fuzzy_match(extracted_data['sector'], VALID_SECTORS)
        if best_match and similarity > 0.85:
            extracted_data['sector'] = best_match
            extracted_data['sector_fuzzy_matched'] = True
        else:
            extracted_data['sector'] = None
            extracted_data['sector_error'] = f"'{extracted_data['sector']}' not in picklist"
    
    return extracted_data
```

### Layer 3: For ICP matching specifically

The ICP Tagging System v7 has 95 cross-matching rules that depend on exact picklist values. When generating ICP tags for the playbook pipeline:

1. Load the complete picklist from `references/icp-tagging.md`
2. Include the full picklist in the Step 2 system prompt
3. Run `validateExtraction()` on every extracted value
4. Log any values that were corrected or stripped
5. If more than 20% of values needed correction, re-run the extraction with a stricter prompt

## Applicable Pipeline Steps

- **Step 1:** Company sector and sub-sector classification
- **Step 2:** ICP tagging for investor matching
- **Step 3:** Grant program categorization
- **Step 5:** Expert specialization matching
- **Phase 2:** DEBRIEF extraction integration (already has this fix deployed)
