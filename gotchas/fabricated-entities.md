# Gotcha: Fabricated Entities

## The Problem

LLMs generate plausible-sounding investor names, fund names, and company names that don't exist. In a playbook shown to a client, one fabricated entity destroys credibility for everything else on the page. The client WILL Google the investors you name.

## Examples of Fabrication

These are the kind of names models generate:
- "Baruch Future Ventures" (sounds like a real fund, isn't)
- "EcoMed Capital" (plausible healthcare cleantech fund name, doesn't exist)
- "August Fern" (plausible investor name, fabricated)

These names are dangerous because they SOUND real. They follow naming conventions of actual funds. A client might not check the first one, but they'll check by the third.

## The Fix

### Investor names: MUST come from the SQLite database
Every investor name in the playbook must have a `db_id` field tracing to a real record. The only exception is if a web search during Step 2 discovers a new investor not in the DB, in which case the source URL is required and the entry gets flagged as "new discovery, not in ClimateDoor network."

### Fund names: MUST come from DB or verified web source
Same rule. The fund must have a website you can link to. If you can't find a fund website, the fund doesn't go in the playbook.

### Company names (competitors, buyers): MUST have a website
Every company mentioned in Step 4 (market intelligence) must have a verified website URL. If you can't find a website, the company doesn't go in the playbook.

### Expert names: MUST come from the expert database
The 28-contact expert DB is the source of truth. Do not generate expert bios. Pull them from the DB and enrich with LinkedIn.

## Verification Checklist (Post-Generation)

Run this after Step 7 assembly:

```python
def verify_entities(playbook_data):
    errors = []
    
    # Check all investor names against DB
    for investor in playbook_data['investors']:
        if 'db_id' not in investor or investor['db_id'] is None:
            if 'source_url' not in investor or not url_resolves(investor['source_url']):
                errors.append(f"FABRICATED INVESTOR: {investor['name']} has no db_id and no verified URL")
    
    # Check all fund names have websites
    for investor in playbook_data['investors']:
        if 'fund_url' not in investor or not url_resolves(investor['fund_url']):
            errors.append(f"UNVERIFIED FUND: {investor['fund']} has no verified website")
    
    # Check all competitor names have websites
    for competitor in playbook_data['market']['competitors']:
        if 'website' not in competitor or not url_resolves(competitor['website']):
            errors.append(f"UNVERIFIED COMPETITOR: {competitor['name']} has no verified website")
    
    # Check all expert names against DB
    for expert in playbook_data['experts']:
        if 'db_id' not in expert or expert['db_id'] is None:
            errors.append(f"FABRICATED EXPERT: {expert['name']} not found in expert database")
    
    return errors
```

## If Verification Fails

Do NOT silently remove the fabricated entity. Instead:
1. Log the failure
2. Replace with a placeholder: "1 additional investor match pending verification"
3. Flag for manual review
4. Never show unverified entities to clients
