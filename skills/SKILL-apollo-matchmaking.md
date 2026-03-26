# SKILL: Apollo Matchmaking Engine for Playbook Contact Search

## Purpose
This skill powers the Buyer and Investor contact search in every ClimateDoor Growth Playbook. It takes an ICP1 company's confirmed or researched data and translates it into Apollo People API Search queries that return named, titled decision-makers at relevant organizations. The search is FREE (zero credits consumed). Credits are only used later when staff chooses to enrich contacts with email addresses.

This skill runs during both Phase 1 (pre-call, research-based) and Phase 2 (post-call, confirmed data). The search quality improves in Phase 2 because confirmed data produces tighter filters.

---

## Apollo API Reference

### Endpoint
```
POST https://api.apollo.io/api/v1/mixed_people/search
```

### Headers
```
Content-Type: application/json
Cache-Control: no-cache
x-api-key: [APOLLO_API_KEY]
```

### Key Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `person_titles` | string[] | Job titles to filter by. Use multiple variants of same role. |
| `person_locations` | string[] | Person's location. Format: "Province, Country" or "Country" |
| `person_seniorities` | string[] | Options: senior, manager, director, vp, c_suite |
| `q_organization_keyword_tags` | string[] | Keywords describing the organization. This is the primary matching lever. |
| `organization_num_employees_ranges` | string[] | Company size ranges. Format: "min,max" |
| `organization_locations` | string[] | Where the company is located (distinct from person location) |
| `per_page` | int | Results per page. Max 100. Use 25 for playbook display. |
| `page` | int | Pagination. Start at 1. |

### What the API Returns (Free Search)
- First name (full)
- Last name (partially obfuscated in free search, e.g., "Ma***d")
- Job title (full)
- Organization name (full)
- Organization metadata: has_email, has_phone, has_industry, has_revenue, has_employee_count
- Person location flags: has_city, has_state, has_country
- Last refreshed date
- Apollo person ID (for later enrichment)

### What Requires Credits (NOT used in playbook search)
- Email addresses (1 credit per contact via People Enrichment endpoint)
- Phone numbers (8 credits per contact)
- Full last name reveal

### Critical Rules
- **NEVER call the People Enrichment endpoint during playbook generation.** Free search only.
- **NEVER consume credits without explicit staff approval.** Credits are consumed only when staff clicks "Save contact" in the playbook UI.
- The free search endpoint has a display limit of 50,000 records (100 per page, 500 pages max).
- Rate limits apply. Space requests by at least 1 second between calls.

---

## Search Architecture

Every playbook runs TWO parallel search categories:

### Category 1: BUYERS (ICP3)
People at organizations who could BUY the ICP1 company's product or service.

### Category 2: INVESTORS (ICP2)
People at investment firms whose thesis matches the ICP1 company's stage, sector, and geography.

Each category produces THREE numbers for the concentric circles display:
1. **Total scanned** - `total_entries` from the broadest search
2. **Highly targeted** - `total_entries` from the tightened search
3. **Previewed** - always 20, deduplicated to one contact per firm

---

## BUYER SEARCH LOGIC

### Step 1: Determine Buyer Title Filters
Map the ICP1 company's product/service to the types of people who would BUY it.

**Title mapping by ICP1 sector:**

| ICP1 Primary Sector | Buyer Titles to Search |
|---------------------|----------------------|
| Buildings & Smart Cities | VP Development, VP Construction, VP Procurement, Director of Procurement, Director of Construction, VP Sustainability, Director of Sustainability, Chief Sustainability Officer |
| Energy & Renewables | VP Energy, VP Procurement, Director of Energy, VP Operations, VP Sustainability, Chief Sustainability Officer, Director of Procurement |
| Transportation & Mobility | VP Fleet, VP Operations, VP Procurement, Director of Logistics, VP Sustainability, Director of Transportation |
| Agriculture & Forestry | VP Operations, VP Procurement, Director of Sustainability, VP Agriculture, Director of Procurement |
| Waste & Circular Economy | VP Sustainability, VP Operations, Director of Procurement, VP Supply Chain, Chief Sustainability Officer |
| Water | VP Operations, VP Infrastructure, Director of Procurement, VP Water, Director of Sustainability |
| Carbon Solutions | VP Sustainability, Chief Sustainability Officer, VP ESG, Director of Carbon, VP Procurement |
| Industrial & Manufacturing | VP Procurement, VP Operations, VP Manufacturing, Director of Procurement, VP Sustainability, VP Supply Chain |
| Sustainable Fashion & Textiles | VP Procurement, VP Sustainability, Director of Sourcing, VP Supply Chain, Chief Sustainability Officer |
| Healthcare & Medical Devices | VP Procurement, Director of Procurement, VP Operations, VP Sustainability, Chief Sustainability Officer, Director of Facilities |

**Always include these universal buyer titles regardless of sector:**
- VP Procurement
- Director of Procurement
- VP Sustainability
- Chief Sustainability Officer

### Step 2: Determine Buyer Organization Keywords
Map the ICP1 company's customer segments (if known from call data or research) to organization keywords that describe where buyers work.

**Keyword mapping by ICP1 customer segments:**

| ICP1 Customer Segment | Organization Keywords |
|----------------------|----------------------|
| Real estate developers | real estate developer, property development, residential construction, housing developer |
| Modular builders | modular construction, prefab, offsite construction, modular building |
| Municipalities | municipality, city government, local government, public works |
| Non-profit housing | affordable housing, non-profit housing, community housing, social housing |
| Indigenous communities | (handled by Indigenous tab, not buyer search) |
| Utilities | utility, electric utility, power company, energy provider |
| Mining companies | mining, mineral extraction, resource company |
| Agricultural operations | agriculture, farming, agribusiness, food production |
| Hospitals / healthcare | hospital, healthcare, health system, medical center |
| Corporate enterprise | (use the specific industry from ICP1 sectors served) |

**If customer segments are unknown (Phase 1 with limited research), derive keywords from:**
1. The ICP1 company's own sector (e.g., "green construction" company likely sells to "real estate" and "construction" buyers)
2. The ICP1 company's website description of who they serve
3. The ICP1 company's climate sector types

### Step 3: Determine Buyer Geography
Use the ICP1 company's confirmed or researched geography, expanded by one level:
- If ICP1 is in Quebec: search "Quebec, Canada" AND "Ontario, Canada" (adjacent major market)
- If ICP1 is in BC: search "British Columbia, Canada" AND "Alberta, Canada"
- If ICP1 targets specific expansion markets (from call data): add those
- If ICP1 is pan-Canadian: search "Canada"
- If ICP1 targets US: add relevant US states

### Step 4: Determine Buyer Company Size
Filter to companies large enough to be real buyers:
- Minimum: 51 employees (skip tiny companies that can't make purchasing decisions)
- Use ranges: ["51,200", "201,500", "501,1000", "1001,5000", "5001,10000"]
- For enterprise-focused ICP1s: start at 201+
- For SME-focused ICP1s: include 11-50 range

### Step 5: Construct the Search

**Broad search (for "total scanned" number):**
```json
{
  "person_titles": [ALL mapped titles],
  "person_locations": [ICP1 geography + expanded],
  "q_organization_keyword_tags": [ALL mapped keywords],
  "organization_num_employees_ranges": ["11,50", "51,200", "201,500", "501,1000", "1001,5000", "5001,10000"],
  "per_page": 1,
  "page": 1
}
```
Only need `total_entries` from this. Set per_page to 1 to minimize data transfer.

**Tight search (for "highly targeted" number and actual results):**
```json
{
  "person_titles": [TOP 8 most relevant titles only],
  "person_seniorities": ["vp", "c_suite", "director"],
  "person_locations": [ICP1 primary geography only],
  "q_organization_keyword_tags": [TOP 6 most specific keywords],
  "organization_num_employees_ranges": ["51,200", "201,500", "501,1000", "1001,5000", "5001,10000"],
  "per_page": 25,
  "page": 1
}
```
Run page 1 and page 2 to get 50 results for deduplication.

### Step 6: Deduplicate to 20 Unique Firms
**CRITICAL RULE: One contact per firm. 20 unique firms. No exceptions.**

Deduplication algorithm:
1. Collect all results from page 1 + page 2 (up to 50 contacts)
2. Group by `organization.name`
3. For each organization, pick the BEST contact using this priority:
   - VP/SVP title > Director title > C-suite title (VP is the sweet spot for purchasing decisions)
   - Title containing "Development" or "Procurement" or "Sustainability" > other titles
   - Has verified email (has_email: true) > no email
4. Take the first 20 unique organizations after sorting by relevance
5. If fewer than 20 unique firms after 2 pages, run page 3

---

## INVESTOR SEARCH LOGIC

### Step 1: Determine Investor Title Filters
These are relatively stable across all ICP1 companies:
```json
["Partner", "Managing Partner", "General Partner", "Principal", "Investment Director", "Founding Partner", "Managing Director"]
```

### Step 2: Determine Investor Organization Keywords
Map the ICP1 company's sector and characteristics to fund thesis keywords.

**Primary keywords (always include):**
- "venture capital"
- "cleantech" OR "climate tech" (use both)
- "impact fund" OR "impact investing"

**Sector-specific keywords (add based on ICP1):**

| ICP1 Primary Sector | Additional Fund Keywords |
|---------------------|------------------------|
| Buildings & Smart Cities | "green construction", "sustainable building", "proptech" |
| Energy & Renewables | "clean energy", "renewable energy", "energy transition" |
| Transportation & Mobility | "mobility", "transport", "EV", "fleet electrification" |
| Agriculture & Forestry | "agtech", "sustainable agriculture", "forestry" |
| Waste & Circular Economy | "circular economy", "waste management", "recycling" |
| Water | "water technology", "water treatment" |
| Carbon Solutions | "carbon capture", "carbon removal", "carbon credits" |
| Industrial & Manufacturing | "industrial decarbonization", "advanced manufacturing" |
| Sustainable Fashion & Textiles | "sustainable fashion", "textile innovation" |
| Healthcare & Medical Devices | "healthtech", "medical devices", "healthcare innovation" |

**If ICP1 has Indigenous alignment, ALWAYS add:**
- "indigenous capital", "indigenous investment", "reconciliation"

### Step 3: Determine Investor Geography
- Default: "Canada" (most ClimateDoor clients are Canadian)
- If ICP1 is targeting US market: add "United States"
- If ICP1 has EU connections (LCBA etc.): add "Europe"
- Investor geography is broader than buyer geography because capital flows across borders

### Step 4: Filter to Actual Funds (Not Banks)
**CRITICAL: Filter by organization size to exclude large banks and consulting firms.**
- Use: ["1,10", "11,50", "51,200"]
- This filters OUT organizations like RBC Capital Markets (90,000+ employees) and keeps actual VC/PE funds
- Most dedicated cleantech funds have 5-50 employees

### Step 5: Construct the Search

**Broad search:**
```json
{
  "person_titles": ["Partner", "Managing Director", "Principal", "Managing Partner", "General Partner", "Investment Director"],
  "person_locations": ["Canada"],
  "q_organization_keyword_tags": ["cleantech", "climate", "sustainability", "clean energy", "impact investing", "renewable energy"],
  "per_page": 1,
  "page": 1
}
```

**Tight search:**
```json
{
  "person_titles": ["Partner", "Managing Partner", "General Partner", "Principal", "Investment Director", "Founding Partner"],
  "person_locations": ["Canada"],
  "q_organization_keyword_tags": [sector-specific keywords from mapping above],
  "organization_num_employees_ranges": ["1,10", "11,50", "51,200"],
  "per_page": 25,
  "page": 1
}
```

### Step 6: Deduplicate to 20 Unique Funds
Same one-per-firm rule as buyers.

Priority for picking the best contact per fund:
- Managing Partner/General Partner/Founding Partner > Partner > Principal > Investment Director
- Title containing sector keywords > generic title
- Has email > no email

---

## CONTACT CARD OUTPUT FORMAT

Each contact in the playbook displays as a card with this structure:

```
[Avatar Initials]
Name: [First Name] [Obfuscated Last Name]
Title: [Full Job Title]
Organization: [Full Org Name]
Fit Note: [1-2 sentence explanation of why this contact/org matches the ICP1 company]

[Action Button: "Begin outreach" or "Activate with Growth Pod"]
[Action Button: "Save contact"]
```

### Fit Note Generation
The fit note is AI-generated and must reference SPECIFIC alignment between the buyer/investor org and the ICP1 company. Never generic.

**Good fit notes:**
- "Quebec-based developer with sustainability mandate. Modular and green building focus matches PakVille panels directly."
- "Circular economy fund. Thesis directly aligned with PakVille's recycled PET core technology."
- "BC's provincial strategic investment fund. PakVille's Vancouver expansion plans create direct geographic fit."

**Bad fit notes (never do this):**
- "Large company that might be interested."
- "Investor in the cleantech space."
- "Relevant organization."

### Action Button Logic
**Phase 1 (pre-call):**
- Warm contacts (CD has existing relationship): "Begin outreach"
- Cold contacts (no CD relationship): "Activate with Growth Pod"

**Phase 2 (post-call):**
- All contacts where deal card includes this service: "Begin outreach"
- Contacts outside deal scope: "Activate with Growth Pod"

**The button labeled "Save contact" replaces "Save to HubSpot" on all external-facing playbooks.** Never expose internal tool names to prospects.

---

## CONCENTRIC CIRCLES DATA

The playbook displays two concentric circle visualizations (buyers and investors), each with three rings:

```
Outer ring:  [broad_search.total_entries] scanned
Middle ring: [tight_search.total_entries] targeted
Inner ring:  20 previewed (always 20, the deduplicated results shown)
```

The inner ring animates on page load, filling proportionally (20/targeted ratio).

Example for PakVille buyers:
- Outer: 1,266 scanned
- Middle: 188 targeted
- Inner: 20 previewed

---

## v7 TAGGING SYSTEM: FIELD MAPPING FOR SAVED CONTACTS

When a contact is saved (after staff approval in Phase 2 or Full Playbook), the following fields map from Apollo data to HubSpot via the v7 ICP tagging system.

### ICP2 (Investor) Field Mapping

| v7 Field | HubSpot Property | Source | Value |
|----------|-----------------|--------|-------|
| First Name | firstname | Apollo | Direct from search |
| Last Name | lastname | Apollo | From enrichment (obfuscated in free search) |
| Email | email | Apollo Enrichment | 1 credit per contact |
| Job Title | jobtitle | Apollo | Direct from search |
| Company Name | company | Apollo | organization.name |
| LinkedIn URL | hs_linkedin_url | Apollo | From enrichment |
| Country/Region | country | Apollo | Person location |
| Avatar (ICP) | avatar___cloned_ | System | "ICP2: Investor" |
| ICP2 Type | icp2_type | AI Inference | Infer from org keywords: VC fund = "ICP 2A", Corporate VC = "ICP 2B", PE = "ICP 2C", Family Office = "ICP 2E", Angel = "ICP 2F" |
| Cheque Size | contact_cheque_size | AI Inference | Estimate from org size and type |
| Industry Preferred | icp2__industry_preferred__new_ | AI Inference | Map from org keywords to v7 picklist values |
| Stage Preferred | stage_of_company_preferred | AI Inference | Default to ICP1 company's stage |
| Preferred Region | preferred_region | AI Inference | "Canada" default, expand if org is multi-geography |
| ICP Warmth | investor_warmth | System | "Cold" (new contact, no CD relationship) |
| Nurture Tier | nurture_tier | System | "Tier 4 - Unknown" |
| Owned by CD/CLI | icp3__owned_by_cd_cli | System | "ClimateDoor" |
| Lead Source | (map to appropriate field) | System | "Apollo" |

### ICP3 (Buyer) Field Mapping

| v7 Field | HubSpot Property | Source | Value |
|----------|-----------------|--------|-------|
| First Name | firstname | Apollo | Direct from search |
| Last Name | lastname | Apollo | From enrichment |
| Email | email | Apollo Enrichment | 1 credit per contact |
| Job Title | jobtitle | Apollo | Direct from search |
| Company Name | company | Apollo | organization.name |
| LinkedIn URL | hs_linkedin_url | Apollo | From enrichment |
| Avatar (ICP) | avatar___cloned_ | System | "ICP3: Partner / Buyer" |
| ICP3 Type | icp3_type | AI Inference | Infer from org employee count: <250 = "ICP3B: SME", 250-2500 = "ICP3B", 2500+ = "ICP3A: Corporate / Enterprise" |
| Buying Role | icp3__buying_role | AI Inference | Infer from title: "VP Procurement" = "Procurement Manager", "VP Sustainability" = "Decision Maker", "Director of Construction" = "Technical Evaluator" |
| Industry Vertical | icp3__looking_for_industries | AI Inference | Map org industry to v7 picklist |
| Company Size | icp3_company_size | Apollo | Map employee count to v7 ranges: <250 = "SME", 250-2500 = "Mid-Market", 2500+ = "Enterprise" |
| City | city | Apollo | Person city |
| State/Province | state | Apollo | Person state |
| Country/Region | country | Apollo | Person country |
| Lead Source | lead_source | System | "Apollo" |
| Sourced by CD/CLI | icp3__sourced_by_cd_cli | System | "ClimateDoor" |
| Nurture Tier | nurture_tier | System | "Tier 4 - Unknown" |
| Matched ICP1 Companies | icp3_matched_icp1 | System | Name of the ICP1 company this playbook is for |
| Deal Stage (Buyer) | icp3_deal_stage | System | "Match Identified" |

### Fields That Stay Empty Until Engagement
These are NOT populated during playbook generation. They require human interaction:
- ICP3: Primary Need
- ICP3: Climate Use Case(s)
- ICP3: Stage of Readiness
- ICP3: Procurement Timeline
- ICP3: Budget / Resourcing
- ICP3: ESG/Regulatory Driver
- ICP3: Net Zero Target Year
- Success Fee Agreement
- Estimated Buyer Deal Value
- Relationship Notes
- ICP2: Investment Type
- ICP2: Lead Investor?
- ICP2: Hardware/Software
- ICP2: # Climate Tech Investments
- What they're looking for

---

## SEARCH QUALITY RULES

### Do
- Always run the broad search first (per_page: 1) to get the total_entries number for the outer concentric circle
- Always run 2 pages of the tight search to have enough contacts for deduplication
- Always deduplicate to exactly 20 unique firms
- Always generate specific, non-generic fit notes referencing the ICP1 company's actual product/sector
- Always include both buyer AND investor searches in every playbook
- In Phase 2, use confirmed data from DEBRIEF extraction to tighten search parameters
- Include "include_similar_titles": true (the default) to catch title variants

### Do Not
- NEVER consume credits (no People Enrichment calls) during playbook generation
- NEVER show more than 1 contact per organization
- NEVER include organizations with fewer than 11 employees in buyer search
- NEVER include organizations with more than 200 employees in investor search (filters out banks)
- NEVER use generic fit notes
- NEVER show "Save to HubSpot" on external-facing playbooks. Use "Save contact" instead
- NEVER expose Apollo as a data source to prospects. The playbook says "ClimateDoor Intelligence" and "275M+ B2B contact database"
- NEVER hardcode search parameters. Always derive them from the ICP1 company's data

---

## EXAMPLE: PakVille

### Input Data (from Phase 1 research or Phase 2 DEBRIEF)
```json
{
  "company_name": "PakVille",
  "primary_sector": "Buildings & Smart Cities",
  "climate_sector_types": ["Green Construction", "Circular Economy", "Recycling / Waste", "Biomaterials"],
  "venture_stage": "Seed",
  "geography": "Quebec, Canada",
  "expansion_markets": ["British Columbia, Canada"],
  "customer_segments": ["Real estate developers", "Modular builders", "Municipalities", "Non-profit housing", "Indigenous communities"],
  "raise_amount": "$2M",
  "team_size": 8,
  "has_indigenous_alignment": true
}
```

### Generated Buyer Search (Tight)
```json
{
  "person_titles": ["VP Development", "VP Construction", "VP Procurement", "VP Sustainability", "Director of Procurement", "Director of Construction", "Director of Sustainability", "Chief Sustainability Officer"],
  "person_seniorities": ["vp", "c_suite", "director"],
  "person_locations": ["Quebec, Canada", "British Columbia, Canada"],
  "q_organization_keyword_tags": ["real estate developer", "residential construction", "housing developer", "property development", "affordable housing", "modular construction"],
  "organization_num_employees_ranges": ["51,200", "201,500", "501,1000", "1001,5000", "5001,10000"],
  "per_page": 25,
  "page": 1
}
```

### Generated Investor Search (Tight)
```json
{
  "person_titles": ["Partner", "Managing Partner", "General Partner", "Principal", "Investment Director", "Founding Partner"],
  "person_locations": ["Canada"],
  "q_organization_keyword_tags": ["cleantech fund", "climate venture", "impact fund", "circular economy", "green construction", "sustainable materials", "indigenous capital"],
  "organization_num_employees_ranges": ["1,10", "11,50", "51,200"],
  "per_page": 25,
  "page": 1
}
```

### Results (from live Apollo test, March 2026)
- Buyer broad: 1,266 total
- Buyer tight: 188 total, 20 unique firms previewed
- Investor broad: 1,913 total (refined to 529 with fund-size filter)
- Investor tight: 529 total, 20 unique funds previewed
- Credits consumed: 0

### Top Buyer Firms Found
Adera Development, Anthem Properties, Axiom Builders, Bosa Properties, Brigil (QC), Concert Properties, Construction Dinamo (QC), Conwest Developments, Intracorp Homes, Ledcor, Ledingham McAllister, Magil Construction (QC), Marcon, Mission Group, Peterson Real Estate, QuadReal Property Group, Starlight Investments, Westbank Corp, Westcliff Management (QC), Wesgroup Properties

### Top Investor Funds Found
Achieve Sustainability, Active Impact Investments, ALTERRA, BioApplied Innovation Pathways, Chrysalix Venture Capital, Circular Innovation Fund, Conexus Venture Capital, Cycle Capital, Ecofuel Fund, Emerald Technology Ventures, Evok Innovations, Fondaction Asset Management, Idealist Capital, InBC Investment Corp, Pangaea Ventures, Raven Indigenous Capital Partners, Renew Venture Capital, Renewal Funds, The Inlandsis Fund, Ha/f Climate Design

---

## IMPLEMENTATION NOTES

### API Key Management
- Store the Apollo API key as an environment variable, never hardcoded
- The key is a master key with access to all endpoints
- Rotate the key periodically (Settings > API Keys in Apollo)

### Error Handling
- If Apollo returns 0 results: broaden the search by removing 1-2 keyword tags and retry
- If Apollo returns fewer than 20 unique firms after 3 pages: lower the seniority filter to include "manager" level
- If Apollo API is down: show a "Contact data temporarily unavailable" message in the playbook, not an error

### Performance
- Each search takes 1-3 seconds
- Total for a full playbook (2 broad + 2 tight + pagination): ~10-15 seconds
- Run buyer and investor searches in parallel to halve wall-clock time

### Cost Tracking
- Log every search call with: playbook_slug, search_type (buyer/investor), total_entries, contacts_returned, timestamp
- This data feeds into ROI tracking: how many contacts surfaced per playbook, how many saved, how many converted

---

## CHANGELOG
- v1.0 (March 2026): Initial skill. Buyer + investor search with v7 field mapping.
- Tested live against Apollo API with PakVille data. Results validated.
