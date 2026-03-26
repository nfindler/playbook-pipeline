# Grant Database Reference

## Data Source

The grant database is a live Notion database maintained by Sophie Kennedy and the ClimateDoor team.

**Database:** Canada - Grants and Funding Database
**Notion Database ID:** `1ac588f311298024b65accdfe6377bb1`
**Data Source ID:** `collection://1ac588f3-1129-80d1-bb7c-000b1f467933`
**Access method:** Notion MCP connector (preferred for live queries) or Notion API

## Schema

### Core Fields

| Field | Type | Description |
|---|---|---|
| Grant Name | title | Name of the grant program |
| Categories | multi_select | Sector categories the grant covers |
| Eligible Groups | multi_select | Who can apply |
| Funding Provider | multi_select | Organization providing the funding |
| Funding Type | multi_select | Government level (Federal, Provincial BC/AB, Private) |
| Type of Funding | multi_select | Repayable, Non-Repayable, Tax Credit, Equity, Crowdfunding |
| Intake - NEW | multi_select | Current intake status |
| Application Start Date | date | When the application window opens |
| Application End Date | date | When the application window closes |
| Region | multi_select | Geographic eligibility |
| Website | url | Official program page |
| Past Experience | status | Whether ClimateDoor has used this program before |
| Client History | multi_select | Which ClimateDoor clients have used this grant |
| Funding Contacts | relation | Links to actual people at funding agencies |
| Alert Tiffanee | checkbox | Flag for indigenous-specific grants to alert Tiff |
| Last Updated | last_edited_time | When the record was last modified |

### Category Picklist Values
- Economic Development
- Housing and Infrastructure
- Clean Energy / Environment
- Health
- Agriculture
- Youth
- Community
- Culture
- Storytelling
- Arts
- Language
- Heritage
- Education & Training
- Technology
- Emergency/Disaster Preparedness & Response
- Marine
- Reconciliation
- Food Security
- Entrepreneurship

### Eligible Groups Picklist Values
- Indigenous Specific
- Remote Communities
- For-Profit
- Non-Profit
- Student
- Women
- Youth
- Community Foundations of Canada
- Seniors
- Indigenous Governments
- Regional Districts
- Education Organization
- Nunavut Business

### Intake Status Picklist Values
- Ongoing (always accepting)
- Application Window Applies (has specific dates)
- Upcoming (not yet open)
- Quarterly Intake
- Monthly Intake
- Continuous
- Open
- Closed
- Closed Until Further Notice
- Ended Permanently

### Region Picklist Values
- Okanagan
- Northern BC
- Vancouver Island
- Ontario
- Alberta
- BC
- Canada (national)
- Northern Canada
- Nunavut
- Northern Ontario
- Manitoba

### Funding Provider Picklist Values
- McConnel Foundation
- ISC (Indigenous Services Canada)
- Telus
- Community Foundations
- WorkBC
- Government of Canada
- Natural Resources Canada
- CMHC
- BC Government
- EMC
- Habitat Conservation Trust Foundation
- NRT
- IAF
- CanNor
- Nunavut Government

### Pre-filtered Views Available
- **All Grants** (default view)
- **Indigenous Specific** (filtered by Eligible Groups = "Indigenous Specific")
- **Clean Energy** (filtered by Categories = "Clean Energy / Environment")
- **Housing and Infrastructure** (filtered by relevant category)
- **Government Funding** (filtered by funding type)

## Query Patterns for Step 3

### Basic match query (via Notion search)
For a company in the Clean Energy sector, based in Canada, that is For-Profit:
1. Search the data source for grants matching the company's sector category
2. Filter by Eligible Groups that include the company's organization type
3. Filter by Intake - NEW that is NOT "Closed", "Closed Until Further Notice", or "Ended Permanently"
4. Filter by Region that includes the company's geography

### Enrichment layer
For each matched grant:
1. Check `Past Experience` field: "Previous Experience" means ClimateDoor has done this before (powerful credibility signal)
2. Check `Client History` field: specific client names that have used this grant (even more powerful)
3. Check `Funding Contacts` relation: actual people at the funding agency ClimateDoor knows
4. Check `Website` field: scrape this URL for CURRENT amounts, deadlines, and eligibility changes

### ICP4 (Indigenous) special handling
If the company has indigenous connections or the opportunity involves indigenous communities:
1. Use the "Indigenous Specific" pre-filtered view
2. Check `Alert Tiffanee` for grants Tiff has flagged
3. Look for grants where indigenous communities are the APPLICANT and the company is a supplier (grants as BD tool pattern)

## Two-Layer Architecture

### Layer 1: Notion Query (institutional knowledge)
- Which programs exist and what are their criteria
- Which programs has ClimateDoor used successfully before
- Which programs has ClimateDoor used for THIS type of company before
- Contact relationships at funding agencies

### Layer 2: Web Scrape (current status)
For each program matched in Layer 1, hit the `Website` URL to verify:
- Current dollar amounts (these change between program years)
- Current intake window status (may have changed since Notion was last updated)
- Updated eligibility criteria (programs evolve)
- Specific deadlines if applicable
- Any recent program announcements

### Layer 3: Web Discovery (new programs)
Scan for programs NOT in the Notion database:
- NRCan funding announcements page
- IRAP current programs
- Provincial innovation agency pages for the company's province
- SIF/SDTC if applicable
- Emerging programs announced in recent government budgets

If new programs are found, flag them for Sophie to add to the Notion database.

## Output Format

Each grant in the playbook output must include:
- Program name and agency (from Notion)
- Dollar range (from web scrape, with scrape date)
- Intake status (from web scrape, cross-checked with Notion)
- Eligibility fit assessment (from Sonnet analysis)
- ClimateDoor experience level (from Notion Past Experience + Client History)
- Strategic sequencing recommendation (from Step 6 synthesis)
- Confidence score (based on eligibility fit certainty)

## Gotcha: Staleness

The `Last Updated` field shows when someone last touched the Notion record. If a grant record hasn't been updated in 3+ months, treat ALL fields except Grant Name and Website as potentially stale. Rely more heavily on the web scrape layer for that program.

Never output a dollar amount or deadline from the Notion database alone without web verification. The Notion data tells you WHERE to look. The web scrape tells you WHAT's current.
