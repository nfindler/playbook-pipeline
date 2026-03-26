# Gotcha: Grant Data Staleness

## The Problem

Grant program details change frequently. Dollar amounts shift between program years. Intake windows open and close. Eligibility criteria get revised. Programs get renamed, merged, or discontinued. A playbook that says "IRAP provides $200-400K" when the program just changed its maximum to $500K undermines trust instantly.

## The Rule

**Never output a dollar amount, deadline, or eligibility criterion from any cached source alone.**

The Notion grant database tells you WHICH programs to look at. The web scrape tells you WHAT those programs look like RIGHT NOW.

## Prevention Pattern

### For every grant in the playbook output:

1. **Query Notion** for the program record (Layer 1: institutional knowledge)
2. **Hit the program's Website URL** to verify current details (Layer 2: live verification)
3. **Compare** the Notion data with the web data
4. **Use the web data** for dollar amounts, deadlines, and intake status
5. **Use the Notion data** for ClimateDoor experience (Past Experience, Client History, Funding Contacts)
6. **Flag discrepancies** between Notion and web data for Sophie to update

### If the program website can't be reached:

- HTTP timeout or 404: Flag the entire grant as "program page unavailable, details unverified"
- Don't fall back to the Notion data alone for amounts/deadlines
- Don't use training data as a substitute
- DO still include the grant if the Notion record shows Past Experience or Client History (the institutional knowledge is still valuable)

### Staleness indicators:

- `Last Updated` field in Notion is 3+ months old: treat all fields as potentially stale
- Intake status shows "Upcoming" but Application Start Date is in the past: likely stale
- Dollar amounts are round numbers ending in K or M: probably correct but verify
- Specific dollar amounts with cents: almost certainly from an actual program page, more trustworthy

## In the playbook HTML output:

Each grant card should display:
- Dollar amounts with a "verified [date]" tag showing when the web scrape ran
- A subtle "(from program website)" attribution on amounts and deadlines
- A warning style if the information couldn't be verified

## Example

Good: "IRAP: $200-500K (verified from nrc.canada.ca, March 2026)"
Bad: "IRAP: $200-400K" (no source, might be from training data or stale Notion record)
