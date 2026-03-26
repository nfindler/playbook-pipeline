# ICP Tagging System v7 Reference

Source: ClimateDoor Master ICP Tagging System v7 (ICP1 - Climate Ventures). This contains every picklist value, HubSpot property name, extraction rule, and matchmaking logic for classifying ICP1 companies and matching them to ICP2-6.

## ICP Architecture

| ICP | Type | Description |
|---|---|---|
| ICP1 | Climate Companies | The companies ClimateDoor serves as clients |
| ICP2 | Investors | Funds, angels, family offices, government capital |
| ICP3 | Cleantech Buyers | Organizations that buy climate technology |
| ICP4 | Indigenous Communities | First Nations, Metis, Inuit communities and organizations |
| ICP5 | Experts/Ambassadors | Domain experts, advisors, Growth Pod specialists |
| ICP6 | Government | Federal, provincial, municipal government contacts |

---

## ICP1 CONTACT BASICS

| Field | Type | HubSpot Property | Notes |
|---|---|---|---|
| Company Name* | Text | `company` | Required |
| Domain Name (URL) | Text | `website` | |
| First Name | Text | `firstname` | |
| Last Name | Text | `lastname` | |
| Job Title | Text | `jobtitle` | |
| Email* | Text | `email` | Required |
| Phone Number | Text | `phone` | |
| LinkedIn URL | Text | `hs_linkedin_url` | |
| CD Rep (Owner) | HubSpot Owner | `hubspot_owner_id` | |

### Company Role (Intake)
HubSpot: `icp1_company_role` | Single Select
```
Founder
Decision Maker
Business Dev Lead
Champion
Technical Buyer
Other
```

### Lifecycle Stage
HubSpot: `lifecyclestage` | Single Select
```
Subscriber
Lead
Marketing Qualified Lead
Sales Qualified Lead
Opportunity
Customer
Evangelist
Other
```

---

## ICP1 CLASSIFICATION (Core Matchmaking Fields)

### Avatar (Master ICP Classifier)
HubSpot: `avatar___cloned_` | Single Select
```
ICP1: Climate Executive
ICP2: Investor
ICP3: Partner / Buyer (Industry)
ICP4: Indigenous
ICP5: Ecosystem / Ambassador / Connector
Government
Competitor
Other - Not Listed
Candidate / Expert
Marketing / Media
Global Ambassador
```

### ICP1 Type
HubSpot: `icp1_type` | Multi Select | AUTO-EXTRACT
```
ICP 1A: Growth-Stage Ventures (60%)
ICP 1B: Near-Commercial Ventures (30%)
ICP 1C: Incubation Opportunities (10%)
Other
```
**Rule:** Active customers = 1A. Pilot/POC/LOI only = 1B. Idea stage = 1C. Evidence required.

### CD Service Type
HubSpot: `cd_service_type` | Multi Select | AUTO-EXTRACT
```
Capital
Grants
Sales/Partnerships
Indigenous
EU LCBA
Marketing
Ops-as-a-Service
Other
```
**Rule:** Only select if transcript explicitly shows need.

### ICP1 Primary Sector (KEY MATCHMAKING FIELD)
HubSpot: `icp1_primary_sector` | Single Select | AUTO-EXTRACT
```
Ag & Food
Buildings & Smart Cities
Carbon
Circular Economy
Clean Industry / Advanced Manufacturing
Climate Intelligence & Software
Digital Services
Energy & Storage
Finance Policy & Markets
Nature-based & Community Solutions
Transportation
Water & Decontamination
Other
```
**Matchmaking:** Maps to ICP2 Industry Preferred, ICP3 Industry Vertical, ICP6 Sector Focus.

### ICP1 Climate Sector Type (Granular Tech Tags)
HubSpot: `icp1_climate_sector_type` | Multi Select | AUTO-EXTRACT
```
Agriculture
AI
Batteries
Biofuel
Biomass
Biomaterials
Carbon Capture
Carbon Markets
Circular Economy
Critical Minerals
Direct Air Capture
Electric Vehicles
Energy
Energy Storage
Family Office
Food / Beverage Tech
Green Construction
Hydrogen
Infrastructure
Institutional
Manufacturing
Mining / Critical Minerals
Ocean Tech
Recycling / Waste
Recycling Technologies
Solar
Transportation
Water
Water Treatment
Wind
Other
```
**Matchmaking:** Maps to ICP3 Technology Interest, ICP4 Clean Tech Interest.

### ICP1 Sectors Served (WHO they sell to)
HubSpot: `icp1_sectors_served` | Multi Select | AUTO-EXTRACT
```
Agriculture and Farming
Aviation
Carbon Markets and Offsetting
Cement and Steel
Chemicals and Green Chemistry
Circular Economy and Materials Recovery
Climate Adaptation and Resilience
Commercial Buildings
Controlled Environment Agriculture (CEA / Greenhouses)
Corporate Partners
Data Centers
District Energy and Heating
Educational Institutions
Electric Vehicles and Charging
Energy Storage
Environmental Consulting
Environmental Remediation and Pollution Control
Fleet and Logistics
Food and Beverage Manufacturing
Food Retail and Distribution
Forestry and Biomass
Green Building and Materials
Grid Infrastructure
Healthcare Facilities
Heavy Industry and Manufacturing
Hydrogen and Bioenergy
Indigenous and Community Organizations
Industrial Facilities
Investors and Family Offices
Land Restoration and Reforestation
Marine and Shipping
Mining and Critical Minerals
Municipalities and Cities
Ports and Logistics Infrastructure
Project Developers and EPCs
Provincial and Federal Government
Ranching and Animal Agriculture
Renewable Energy (Solar Wind Hydro Geothermal)
Residential Construction and Development
Sustainable Packaging
Textiles and Apparel
Transportation Equipment Manufacturing
Utilities (Electric Gas Water)
Waste Management and Recycling
Water and Wastewater Treatment
Other
```
**Matchmaking:** Maps to ICP3 Industry Vertical. Semantic match: "Project developers" = ICP3 Infrastructure. "Enterprise retail" = ICP3 Consumer.

---

## VENTURE STAGE & READINESS

### ICP1 Venture Stage (KEY MATCHMAKING FIELD)
HubSpot: `icp1_venture_stage` | Single Select | AUTO-EXTRACT
```
Pre-seed
Seed
Series A
Series B
Series C+
Bridge
IPO
PubCo
Mezzanine
```
**Rule:** 2-step: Declared from transcript first, Estimated with evidence if not stated. Maps to ICP2 Stage Preferred.

### ICP1 TRL Level
HubSpot: `icp1_trl_level` | Single Select | AUTO-EXTRACT
```
TRL 1-4 (Concept / Prototype)
TRL 5-6 (Validation / Demo)
TRL 7 (Pilot)
TRL 8 (Market Entry)
TRL 9 (Scaling Up)
```
**Rule:** 2-step: Declared first, Estimated with evidence. Affects grant eligibility + buyer confidence.

### ICP1 Revenue
HubSpot: `icp1_revenue` | Single Select | AUTO-EXTRACT
```
Pre-Revenue
<$99k
$100k-$249k
$250k-$499k
$500k-$999k
$1M-$5M
$6M-$10M
$10M+
```
**Rule:** Fill only if revenue/ARR explicitly stated.

### Fund Candidate
HubSpot: `fund_candidate` | Single Select | AUTO-EXTRACT
```
Tier 1
Tier 2
Not Candidate
```
**Rule:** Hardware-only. Software = Not Candidate. Hardware gate: TRL 5-6 + credible pilot. Score /10 on Pilot Prep, CD Need, Authority, Budget, Timing.

---

## WHAT THEY NEED FROM CLIMATEDOOR

### Looking For (CRITICAL TRIGGER FIELD)
HubSpot: `icp1_looking_for` | Multi Select | AUTO-EXTRACT
```
Capital
Grants
Partnerships
Indigenous
Marketing
EU LCBA
Operations
Other
```
**CRITICAL MATCHMAKING TRIGGERS:**
- Capital = activate ICP2 investor matching
- Partnerships = activate ICP3 buyer matching
- Indigenous = activate ICP4 community matching
- Grants = activate ICP6 government + Grant scanning agent

---

## LEAD SOURCE & CONTEXT

### Lead Source
HubSpot: `lead_source` | Single Select
```
Apollo
LinkedIn / Sales Navigator
Crunchbase
Pitchbook
ZoomInfo
Listbuilding - Other
Acquired List
Event
Referral
Partner
Business Development
Inbound: Website
Inbound: LinkedIn
Inbound: Other social
Other
```

---

## QUALITATIVE INTEL (Auto-Extract from Transcript)

These fields are extracted by the DEBRIEF engine from call transcripts:

| Field | HubSpot Property | Extraction Rule |
|---|---|---|
| Company & Team Notes | `icp1_company_team_notes` | Founders, team size, key people, location, technical details, product. Include timestamps. |
| Elevator Pitch | `elevator_pitch_contact` | One-liner. Transcript + website allowed. Used in RADAR briefs. |
| Description | `description` | Company description. Transcript + website allowed. |
| Top 1-3 Objectives | `icp1_top_objectives` | With timestamps. MATCHING: 'Raise capital' = ICP2. 'Enter EU' = ICP3 EU + ICP6 trade + LCBA. 'Indigenous' = ICP4. |
| Biggest Constraints | `icp1_biggest_constraints` | Capital, Customers, Talent, GTM, etc. MATCHING: 'Capital' = ICP2+ICP6. 'Customers' = ICP3. 'GTM' = ICP5 experts. |
| Red Flags | `icp1_red_flags` | 'No clear buyer', 'Want everything free', 'No owner for grants', 'Vague timeline'. Reduces pipeline priority. |
| Demand Creation | `icp1_demand_creation` | 'Founder-led, no BD' = high CD value. '95% referrals' = strong product, weak distribution. |
| What's Working/Not | `icp1_working_not_working` | 'Not working: finding climate investors' = ICP2 priority. 'Not working: cracking mining' = ICP3 mining + ICP5 mining experts. |
| Signed Deals | `icp1_signed_deals` | Boosts ICP2 scoring. Named customers confirm ICP3 sector match. |
| Customer Segments | `icp1_customer_segments` | Semantic match to ICP3 Industry Vertical. |
| Fundraising Notes | `icp1_fundraising_notes` | Round size, structure, lead status, timeline, % committed. Feeds ICP2 filter. |
| Non-Dilutive / Grants Notes | `icp1_grants_notes` | Programs, deadlines, contacts. MATCHING: 'DARPA' = ICP6 US gov. 'NRCan' = ICP6 NRCan contacts. |
| Market Entry Plans | `icp1_market_entry` | 'Entering EU' = ICP3 EU + ICP5 EU + ICP6 trade + LCBA. 'Canadian entity' = Canadian ICP3/ICP6. |
| BD / Partners Objectives | `icp1_bd_objectives` | 'Project developer partner' = ICP3 Infrastructure. 'Distribution' = ICP3 Channel. |
| First Nations Notes | `icp1_first_nations_notes` | Non-empty triggers ICP4 matching. 'Remote communities' = ICP4 diesel-dependent. |

---

## BANT SCORING

| Field | HubSpot Property | Extraction Rule |
|---|---|---|
| Budget | `icp1_bant_budget` | Budget to HIRE CLIMATEDOOR (not capital raised). 'Paid trial' = budget signal. |
| Authority | `icp1_bant_authority` | 'CEO present and driving' = strong. 'Board approval needed' = longer cycle. |
| Need | `icp1_bant_need` | Specific expressed need for CD services. |
| Timing | `icp1_bant_timing` | 'Proposal meeting Wed Jan 28' = urgent. 'Vague' = red flag. |

### Lead Commitment Score
HubSpot: `icp1_commitment_score` | Single Select
```
1/5
2/5
3/5
4/5
5/5
```
**Scoring:** 0-2 per BANT dimension (/8 total). 0-1=1/5, 2-3=2/5, 4-5=3/5, 6-7=4/5, 8=5/5.

---

## REVENUE & SUCCESS FEE TRACKING

### Success Fee Agreement
HubSpot: `icp1_success_fee_agreement` | Multi Select
```
Capital
Grants
Sales
```

### Success Fee %
HubSpot: `icp1_success_fee_pct` | Single Select
```
1%
2%
3%
4%
5%
6%
7%
8%
10%
Custom (see notes)
```
**Typical:** 3-5% for capital. 5-10% for sales.

### Equity Position
HubSpot: `icp1_equity_position` | Single Select
```
Yes
No
Negotiating
```

---

## DEAL PIPELINE

### Deal Stage
HubSpot: `icp1_deal_stage` | Single Select
```
Match Identified
Intro Made
Meeting Held
Proposal / LOI
Deal Closed
Revenue Collected
Lost / Dead
```
**Alert:** Agent flags > 30 days in current stage.

### Lost Reason
HubSpot: `icp1_lost_reason` | Single Select
```
Timing
Budget
Chose competitor
Internal decision
Bad fit
No response
Other
```

---

## CROSS-ICP MATCHMAKING TRIGGERS

These are the critical matchmaking triggers from the ICP1 data that activate searches across other ICP databases:

| ICP1 Field Value | Triggers | Target ICP |
|---|---|---|
| Looking For = "Capital" | Investor matching | ICP2 |
| Looking For = "Partnerships" | Buyer matching | ICP3 |
| Looking For = "Indigenous" | Community matching | ICP4 |
| Looking For = "Grants" | Grant scanning + Government contacts | ICP6 + Notion Grant DB |
| Looking For = "EU LCBA" | EU market entry via LCBA program | ICP3 EU + ICP5 EU + ICP6 trade |
| Primary Sector = X | Filter ICP2 by Industry Preferred = X | ICP2 |
| Climate Sector Type = X | Filter ICP3 by Technology Interest = X | ICP3 |
| Sectors Served = X | Filter ICP3 by Industry Vertical = X | ICP3 |
| Venture Stage = X | Filter ICP2 by Stage Preferred = X | ICP2 |
| First Nations Notes non-empty | Activate ICP4 matching | ICP4 |
| Market Entry = "EU" | Activate LCBA + EU ICP3 + ICP5 EU experts | ICP3, ICP5, ICP6 |
| Biggest Constraints = "Capital" | Priority ICP2 + ICP6 | ICP2, ICP6 |
| Biggest Constraints = "Customers" | Priority ICP3 | ICP3 |
| Biggest Constraints = "GTM" | Priority ICP5 experts | ICP5 |

---

## PICKLIST HALLUCINATION PREVENTION

When extracting ICP tags from any source (web scraping, transcript, or model generation), the model MUST:

1. Include the COMPLETE picklist values from this document in the system prompt
2. After extraction, run validation that strips any value not in the official picklist
3. Log stripped values for monitoring

```python
# Example: Validating ICP1 Primary Sector
VALID_PRIMARY_SECTORS = [
    "Ag & Food", "Buildings & Smart Cities", "Carbon", "Circular Economy",
    "Clean Industry / Advanced Manufacturing", "Climate Intelligence & Software",
    "Digital Services", "Energy & Storage", "Finance Policy & Markets",
    "Nature-based & Community Solutions", "Transportation",
    "Water & Decontamination", "Other"
]

def validate_primary_sector(extracted_value):
    if extracted_value in VALID_PRIMARY_SECTORS:
        return extracted_value
    # Try fuzzy match
    for valid in VALID_PRIMARY_SECTORS:
        if extracted_value.lower() in valid.lower() or valid.lower() in extracted_value.lower():
            log.warning(f"Fuzzy matched '{extracted_value}' to '{valid}'")
            return valid
    log.error(f"INVALID sector: '{extracted_value}' not in picklist")
    return None
```

Apply this pattern to EVERY picklist field. The model will try to generate plausible but non-matching values. The validation function is the safety net.

---

## TODO: Additional ICP Picklists Needed

The following ICP type picklists should be added when their CSV sheets are available:
- [ ] ICP2 (Investors): Investor Type, Industry Preferred, Stage Preferred, Geography, Check Size Range
- [ ] ICP3 (Buyers): Industry Vertical, Technology Interest, Procurement Type, Budget Range
- [ ] ICP4 (Indigenous): Community Type, Region, Clean Tech Interest, Funding Status
- [ ] ICP5 (Experts): Expertise Domain, Geographic Coverage, Functional Specialty
- [ ] ICP6 (Government): Level (Federal/Provincial/Municipal), Department, Program Focus

Nick: Upload the remaining ICP sheets and I'll add them.
