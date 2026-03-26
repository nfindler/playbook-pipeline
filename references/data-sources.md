# Data Sources Reference

All file paths, database locations, API endpoints, and access patterns for the playbook pipeline.

## VPS Infrastructure

**Server:** 143.110.220.41 (DigitalOcean Toronto, Ubuntu 24)
**Web root:** `/var/www/climatedoor/`
**Agent state:** `/home/openclaw/`
**Playbook output:** `/var/www/climatedoor/playbooks/[company-slug]/`

## Databases

### Investor Database (SQLite)
- **Path:** `/home/openclaw/data/investors.db` (confirm exact path on VPS)
- **Record count:** ~2,645 contacts
- **Used in:** Step 2 (Investor Matching)
- **Key tables:** investors (main), investor_tags, investor_deals
- **Key fields:** name, fund, sector_tags, stage_preferences, check_size_min, check_size_max, geography, last_active, hubspot_id, intro_path_type
- **Update frequency:** Synced from HubSpot periodically

### Expert Database (SQLite)
- **Path:** `/home/openclaw/data/experts.db` (confirm exact path on VPS)
- **Record count:** ~28 contacts
- **Used in:** Step 5 (Expert Matching)
- **Key fields:** name, title, bio, sector_expertise, geographic_expertise, functional_expertise, agreement_status, hubspot_id

### Grant Database (Notion, LIVE)
- **Database ID:** `1ac588f311298024b65accdfe6377bb1`
- **Data Source ID:** `collection://1ac588f3-1129-80d1-bb7c-000b1f467933`
- **Access method:** Notion MCP connector or Notion API
- **Used in:** Step 3 (Grant Scanning)
- **See:** `references/grant-db.md` for full schema and query patterns
- **Update frequency:** Live (team updates as part of normal workflow)

### ICP Tagging System v7 (Excel)
- **Location:** Shared drive (exact path TBD)
- **Sheets:** 10 sheets covering all ICP types and cross-matching rules
- **Used in:** Steps 2, 3, 5, 6 (matching logic across all database queries)
- **See:** `references/icp-tagging.md` for extracted picklist values

## APIs and External Services

### HubSpot CRM
- **Used in:** Steps 2, 5 (relationship data, intro path mapping)
- **Key data:** Contact records, deal history, company associations, interaction timeline
- **Access:** HubSpot API (key stored in environment variable)

### Anthropic API (Claude models)
- **Used in:** Steps 1-6 (model calls)
- **Models:**
  - Haiku: Steps 1, 3 (high-volume scanning, ~$0.15/step)
  - Sonnet: Steps 2, 4, 5 (reasoning + matching, ~$0.25-0.30/step)
  - Opus: Step 6 (strategic synthesis, ~$1.50/step)
- **Budget:** ~$2.60 per playbook generation

### Fireflies.ai (Call Transcripts)
- **Used in:** Phase 2+ (post-call playbook evolution)
- **Webhook:** `climatedoor.ai/debrief/api/webhook`
- **Access:** Fireflies API or webhook payload

## Web Scraping Targets by Step

### Step 1: Company Research
- Company website (up to 20 pages)
- Crunchbase: `crunchbase.com/organization/[slug]`
- LinkedIn: `linkedin.com/company/[slug]`
- Google Patents: `patents.google.com/?q=[company+name]`
- Health Canada DPD: `health-products.canada.ca/`
- FDA 510(k): `accessdata.fda.gov/scripts/cdrh/`
- Google News: `news.google.com/search?q=[company+name]`

### Step 3: Grant Scanning (web verification layer)
- NRCan: `nrcan.gc.ca/funding-programs`
- IRAP: `nrc.canada.ca/en/support-technology-innovation`
- Innovate BC: `innovatebc.ca/programs`
- SIF: `ised-isde.canada.ca/site/strategic-innovation-fund`
- BuyAndSell.gc.ca (procurement)
- MERX (if paid account)
- Provincial innovation agency pages (varies by province)
- Each grant's specific `Website` URL from the Notion database

### Step 4: Market Intelligence
- Industry association reports
- Conference event pages
- Competitor websites
- Regulatory agency announcements
- News sources: Canary Media, Inside Climate News, Carbon Credits, FT Climate Capital

## Output File Paths

All intermediate JSON files are stored in a working directory per playbook generation:

```
/home/claude/playbook-data/[company-slug]/
  step1-company.json
  step2-investors.json
  step3-grants.json
  step4-market.json
  step5-experts.json
  step6-synthesis.json
  playbook.html (final output)
  verification-log.json
  generation-metadata.json
```

The final `playbook.html` is then deployed to:
```
/var/www/climatedoor/playbooks/[company-slug]/index.html
```

## SCP Deployment

**SCP always runs from local Mac terminal**, not from Claude Code on the droplet.

```bash
# From Mac terminal:
scp playbook.html root@143.110.220.41:/var/www/climatedoor/playbooks/[company-slug]/index.html
```

Caddy routing uses `try_files {path} {path}/index.html /index.html` pattern.
Use versioned filenames during development to avoid cache confusion.
