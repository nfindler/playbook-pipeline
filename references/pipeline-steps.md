# Pipeline Steps Reference

## Step 1: Company Research

**Model:** Haiku (cheapest, high-volume scanning)
**Input:** Company name, optional website URL
**Output:** `data/step1-company.json`

### Sources to scrape (in order)
1. Company website (every page up to 20 pages deep)
2. Crunchbase profile (funding history, team, description)
3. LinkedIn company page (employee count, recent posts, about)
4. Google Patents search for company name and founder names
5. Regulatory databases: Health Canada DPD, FDA 510(k), EU CE marking
6. News: Google News search for company name, last 12 months
7. Press releases on company domain

### Traction Signal Scan (CRITICAL from evaluation framework)
On the company's website, actively look for:

**Logo scanning:** Go to homepage, about page, and any "partners" or "clients" page. Extract every logo/name visible. Categorize each as:
- Government BUYER logos (DND, DARPA, federal agencies) = massive green flag. This means government due diligence has validated the tech.
- Government FUNDER logos (NRCan, IRAP, SDTC) = good signal but different. This is non-dilutive funding, not buyer traction.
- Enterprise logos (Fortune 500, major corporations) = enterprise validation
- Accelerator/incubator logos (Y Combinator, Techstars, Creative Destruction Lab, MaRS) = selection process validation
- University/research logos = early stage validation

**Military/defense traction:** If ANY government defense logos appear, flag prominently. As the team says: "Military traction means the military looked at their tech and said it's relevant and far enough along to bet government dollars. That's due diligence for civilian use cases too." This is not about military applications. It's about validation quality.

**Revenue indicators:** Look for:
- Case studies with named customers
- "Trusted by" sections
- Customer count claims ("500+ clinics")
- Revenue range if disclosed
- Trial/pilot mentions with conversion data

**Contact person research:** For the specific person the team is meeting:
- LinkedIn profile: current role, career history, education, mutual connections
- Recent LinkedIn posts or articles (conversation starters)
- Conference speaking history
- Personal interests visible on social media

### Output schema
```json
{
  "company": {
    "name": "string",
    "website": "string (source_url)",
    "description": "string",
    "description_source": "url where this was found",
    "founded": "year",
    "stage": "Pre-seed | Seed | Series A | Series B | Growth",
    "stage_source": "url",
    "sector": "from ICP v7 picklist, see icp-tagging.md",
    "sub_sector": "from ICP v7 picklist",
    "trl": "1-9",
    "trl_source": "url or reasoning",
    "geography": {
      "hq": "city, province/state, country",
      "operations": ["list of locations"]
    }
  },
  "product": {
    "description": "string",
    "key_claims": [
      {
        "claim": "82% GHG reduction",
        "source_url": "url to LCA report or page making this claim",
        "verified": true
      }
    ],
    "regulatory_status": {
      "iso_11607": { "status": "certified | pending | unknown", "source_url": "url" },
      "fda_510k": { "status": "cleared | pending | not_applicable | unknown", "source_url": "url" },
      "ce_marking": { "status": "certified | pending | unknown", "source_url": "url" },
      "health_canada": { "status": "string", "source_url": "url" }
    },
    "ip": {
      "patents": [
        { "title": "string", "number": "string", "jurisdiction": "string", "source_url": "url" }
      ]
    }
  },
  "funding": {
    "total_raised": "dollar amount",
    "total_raised_source": "url",
    "current_raise": {
      "amount": "dollar amount",
      "stage": "string",
      "use_of_funds": "string if known",
      "source_url": "url"
    },
    "rounds": [
      { "date": "string", "amount": "string", "type": "string", "investors": ["list"], "source_url": "url" }
    ]
  },
  "team": {
    "founders": [
      { "name": "string", "title": "string", "linkedin": "url", "background_summary": "string" }
    ],
    "employee_count": "number",
    "employee_count_source": "url"
  },
  "market": {
    "target_buyers": ["list of buyer types mentioned on their site"],
    "competitors_mentioned": ["any competitors they reference"],
    "market_size_claims": [
      { "claim": "string", "source_url": "url", "verified": true }
    ]
  },
  "traction": {
    "website_logos": [
      {
        "name": "Organization name",
        "type": "government_buyer | government_funder | enterprise | accelerator | university | other",
        "significance": "Why this matters (e.g., 'DARPA logo indicates military due diligence validation')",
        "source_url": "url of the page where logo was found"
      }
    ],
    "government_buyer_traction": true,
    "military_defense_traction": false,
    "customer_count": { "claimed": "500+ clinics", "source_url": "url", "verified": true },
    "case_studies": [
      { "customer": "string", "outcome": "string", "source_url": "url" }
    ],
    "trial_conversion_data": { "rate": "70%", "source_url": "url", "verified": true }
  },
  "signals": {
    "recent_news": [
      { "headline": "string", "date": "string", "source_url": "url", "relevance": "string" }
    ],
    "partnerships": [
      { "partner": "string", "type": "string", "source_url": "url" }
    ],
    "sector_temperature": {
      "assessment": "hot | warming | stable | cooling | cold",
      "evidence": ["Specific evidence points with source URLs"],
      "competitor_funding": [
        { "competitor": "string", "round": "string", "amount": "string", "investor": "string", "date": "string", "source_url": "url" }
      ]
    }
  },
  "contact_person": {
    "name": "string",
    "title": "string",
    "linkedin_url": "url",
    "career_summary": "2-3 sentences on their background",
    "recent_activity": "Recent posts, articles, or speaking engagements",
    "mutual_connections": ["Names of shared connections with ClimateDoor team"],
    "rapport_notes": "Personal interests, hobbies, shared geographic/educational background"
  },
  "data_gaps": [
    "List of things we looked for but couldn't find. These become Key Questions."
  ],
  "generation_metadata": {
    "generated_at": "ISO timestamp",
    "sources_checked": 7,
    "sources_reached": 5,
    "claims_verified": 12,
    "claims_unverified": 3
  }
}
```

### Gotchas for Step 1
- If the company website is a single-page site, try the Wayback Machine for older versions with more content
- LinkedIn employee counts are estimates, flag as approximate
- Patent searches should include both company name AND founder names (founders often file patents personally)
- If Crunchbase shows no funding data, DO NOT assume bootstrapped. Flag as "funding data unavailable"
- Regulatory status "unknown" is a valid and important output. Don't guess.
- Government logos on the website are the highest-signal traction indicator. Don't skip the logo scan.
- Sector temperature should use data from the last 6 months, not general sector knowledge
- Contact person research is for the call prep, not for the playbook itself. Keep it separate.


## Step 2: Investor Matching

**Model:** Sonnet (needs reasoning for thesis analysis + web verification)
**Input:** `data/step1-company.json` + investor SQLite DB + ICP v7 rules + HubSpot
**Output:** `data/step2-investors.json`
**Cost:** ~$0.50 (higher than other steps due to multi-pass + web verification)

### CRITICAL: Read `investor-scoring.md` for the complete methodology

This step uses a 5-pass matching architecture, NOT a single SQL query. See `investor-scoring.md` for full details. Summary:

**Pass 1:** Direct sector match (company's primary and sub-sectors against investor thesis tags)
**Pass 2:** Stage + geography match regardless of sector (catches active generalists)
**Pass 3:** Adjacent sector match (using the sector adjacency map in investor-scoring.md)
**Pass 4:** Impact thesis match (outcome-based investors: GHG reduction, waste diversion, etc.)
**Pass 5:** Relationship-first match (strongest HubSpot relationships regardless of sector)

Merge all passes, de-duplicate, apply multi-dimensional match bonus, then score with the 6-factor weighted formula.

### After scoring: Web verification for top 15

For each of the top 15 scored matches, Sonnet runs a web search to verify:
1. Is the fund still active? (check for deals in last 12 months)
2. What is their current deployment status? (actively investing vs. fully deployed)
3. Any recent thesis papers, blog posts, or interviews about relevant sectors?
4. Any portfolio companies that create synergy or conflict?
5. Which partner covers the relevant sector? (target the specific person for intro)
6. Any recent exits in adjacent space? (signals appetite to double down)

Web verification can change scores up or down. Disqualify funds that are inactive 24+ months, have direct portfolio conflicts with stated "one bet per sector" policy, or where the DB record is clearly outdated.

### Intro path mapping (from HubSpot)

Query HubSpot for EVERY investor in the top 15 and map:
- Direct relationship with anyone at the fund (warm) with SPECIFIC PERSON NAME
- Shared connections (network) with SPECIFIC PERSON NAME
- Co-investor overlap with ClimateDoor portfolio (network)
- Conference overlap in last 2 years (warm via event) with SPECIFIC EVENT NAME
- No connection found (cold/research)

An intro path without a specific person name is not a valid intro path. "Via network" is not acceptable. "Via Sarah Chen at BDC, who co-invested with [Fund] in [Deal]" is.

### Output schema per investor
```json
{
  "name": "string (from DB, never fabricated)",
  "fund": "string (from DB)",
  "score": 85,
  "score_breakdown": {
    "thesis_fit": 25,
    "stage_fit": 20,
    "geography_fit": 15,
    "intro_warmth": 15,
    "fund_activity": 10
  },
  "action_level": "act_now | know | watch",
  "check_size": "$1M-$4M (from DB or web)",
  "thesis_summary": "2-3 sentences (verified by web search)",
  "intro_path": {
    "type": "warm | network | cold",
    "detail": "Specific connection from HubSpot",
    "source": "hubspot | conference_overlap | co_investor | none"
  },
  "approach": "2-3 sentences on how to position for this specific investor",
  "insights": ["Bullet points connecting this investor to the company's specific situation"],
  "verified": true,
  "db_id": "the ID from the SQLite database"
}
```


## Step 3: Grant Scanning

**Model:** Haiku (scanning) then Sonnet (eligibility analysis)
**Input:** `data/step1-company.json` + internal grant database + live web scraping
**Output:** `data/step3-grants.json`

### Two-source approach:

**Source A: Internal grant database**
Query the grant DB (see `grant-db.md` for schema) by:
- Sector match
- Stage/TRL match
- Geography match
- Organization type match
Filter to programs that are currently active (not closed).

**Source B: Live web scraping**
For each matched program from Source A, scrape the official program page to get:
- Current dollar amounts (these change between intakes)
- Current intake window status (open, closed, upcoming)
- Current eligibility criteria (may have been updated)
- Application deadline if applicable

Also scan for NEW programs not in the DB:
- NRCan funding page
- IRAP current programs
- Provincial innovation agency pages for company's province
- SDTC/SIF if applicable

### Eligibility analysis (Sonnet)
For each grant, explicitly check each eligibility criterion against the company data:
- Does the company meet the size requirement?
- Does the technology/product match the program scope?
- Does the geography qualify?
- Are there any disqualifying factors?

If ANY criterion is uncertain, flag it and add to Key Questions.

### Output schema per grant
```json
{
  "program_name": "string",
  "agency": "string",
  "program_url": "url (scraped and confirmed accessible)",
  "amount_range": "$200K-$400K",
  "amount_source": "url where this number was found",
  "amount_scraped_date": "ISO date",
  "intake_status": "open | closed | upcoming",
  "next_deadline": "date or 'rolling'",
  "eligibility_fit": "strong | moderate | weak | uncertain",
  "eligibility_details": [
    { "criterion": "SME under 500 employees", "met": true, "source": "Step 1 employee count" },
    { "criterion": "BC-based operations", "met": false, "flag": "Frett is Quebec-based, BC nexus unclear" }
  ],
  "strategic_value": "2-3 sentences on how this grant fits the broader strategy",
  "climatedoor_experience": "Has ClimateDoor successfully used this program before? From Sophie's tracking data.",
  "recommended_sequencing": "When to apply relative to other grants",
  "effort_estimate": "low | medium | high",
  "confidence": 0.8,
  "confidence_reasoning": "Strong fit on criteria. Main uncertainty is BC nexus requirement."
}
```

### Grants-as-BD-Tool Pattern (CLIMATEDOOR DIFFERENTIATOR)

This is the most differentiated angle ClimateDoor has in the grants space. For every company, answer this question:

**"Can the company's END CUSTOMER get a grant that pays for the company's services?"**

This flips the sales model entirely. Instead of the company selling, their customer gets funded to buy.

Research pattern:
1. From Step 1, identify the company's end customers (buyer types)
2. For each buyer type, search the grant database for programs those buyers can access
3. Check if the company's product/service qualifies as an eligible expense under those programs
4. If yes, this becomes a separate output section in the grants JSON

Example: WildTac DNA makes species detection tools. Their customers (indigenous communities, municipalities) can get nature tech grants to pay for WildTac's services. The company doesn't need to sell harder. Their customer gets funded to buy.

Output schema for grants-as-BD entries:
```json
{
  "type": "grants_as_bd",
  "customer_type": "Indigenous communities",
  "grant_program": "Nature Smart Climate Solutions Fund",
  "program_url": "url",
  "customer_eligibility": "Indigenous governments and organizations",
  "how_it_works": "Community applies for habitat monitoring funding. Budget line includes species detection services. WildTac fulfills as the service provider.",
  "estimated_value": "$50K-200K per community application",
  "climatedoor_advantage": "ICP4 relationships with indigenous communities who would be the applicants"
}
```


## Step 4: Market Intelligence

**Model:** Sonnet (needs reasoning for analysis)
**Input:** `data/step1-company.json` + web research
**Output:** `data/step4-market.json`

### Research areas:

Read `market-research-rules.md` for the complete sourcing requirements including the Unique Angle Research section. The unique angles (geographic, national security, grants-as-BD, sector temperature) are what separate a ClimateDoor playbook from a generic research report.

**Buyer segments** - Identify 3-5 buyer types with:
- Named organizations where possible
- Procurement structure (centralized vs. distributed)
- Decision maker titles
- Estimated sales cycle length
- ACV potential (with methodology)

**Market signals** - Find 3-6 signals with:
- What's happening (regulatory, competitive, procurement trend)
- When (specific dates, deadlines, timelines)
- Source URL for each signal
- Relevance to the company (1-2 sentences)
- Action level: ACT NOW / KNOW / WATCH

**Competitive landscape** - Find 3-5 competitors with:
- Company name and what they do
- How they differ from the target company
- Strengths and weaknesses relative to target
- TRL / deployment status

**Conference targets** - Find 3-5 events with:
- Event name, date, location
- Expected attendee count (from event website)
- Why it's relevant (buyer overlap, investor presence)
- Fit score (methodology: attendee_overlap * buyer_density * recency)

**Indigenous partnership opportunities** - Check EVERY company for ICP4 angles:
This is a systematic check, not an afterthought. If there's no fit, that's fine. If there is, it's often the most powerful angle in the playbook.

Research questions:
1. Could this technology serve remote or off-grid Indigenous communities? (energy, housing, water, waste, food security, transportation)
2. Are there Indigenous-specific grants that could fund deployment of this technology?
3. Does the company have any existing Indigenous partnerships or mentions?
4. Are there specific communities in the company's geography with published needs matching this tech?
5. Could an Indigenous community or organization be the END CUSTOMER whose grant funds the company's services? (grants-as-BD-tool pattern)

For each identified opportunity, output:
```json
{
  "community_or_org": "Name (or type if specific community not identified)",
  "region": "Province / territory / specific area",
  "opportunity_type": "direct_deployment | grants_as_bd | partnership | procurement",
  "fit_score": 78,
  "narrative": "3-5 sentences explaining the partnership opportunity",
  "intro_path": {
    "type": "tiff_relationship | cd_network | conference | regional_contact | cold",
    "detail": "Specific person or connection path"
  },
  "approach": "Community-first engagement strategy. Understand needs, don't pitch product.",
  "grant_pathways": [
    {
      "program": "ISC Clean Energy for Indigenous Communities",
      "relevance": "How this grant funds the deployment",
      "source_url": "url"
    }
  ],
  "action_level": "act_now | know | watch"
}
```

**CRITICAL APPROACH NOTE:** Indigenous partnerships require community-first engagement. The approach box must emphasize:
- Understanding community needs before proposing solutions
- Local employment and capacity building as part of deployment
- Revenue/benefit sharing where applicable (carbon credits, savings)
- Letting the community decide scope and pace of expansion
- Working through existing community leadership structures

**Future state (ICP4 DB with 660+ communities):** When the database is populated, this becomes a multi-pass matching step identical to investor matching but with different dimensions: technology applicability, geographic proximity, published community needs, existing ClimateDoor relationships (via Tiff), and grant pathway availability.

### Market sizing rules
NEVER output a market size number without one of:
1. A cited industry report: "According to [Report Name] by [Publisher], the market is $X"
2. A bottom-up calculation: "N buyers x avg deal size = $X addressable"
3. An explicit "estimated" flag with methodology shown

If you cannot find reliable market sizing data, say "Market size data not publicly available. Bottom-up estimate: [show math]."


## Step 5: Expert Matching

**Model:** Sonnet
**Input:** `data/step1-company.json` + expert SQLite DB (28 contacts) + HubSpot
**Output:** `data/step5-experts.json`

Query expert DB by sector expertise, capability match, and geography. For each match:
- Pull bio from DB (DO NOT generate bios)
- Enrich with current LinkedIn data
- Check HubSpot for agreement status (signed, pending, prospective)
- Write a "Why [Company]" rationale based ONLY on facts from Steps 1-4

Also match the ClimateDoor internal team (Growth Pod):
- Who from the CD team should be assigned based on sector and service type
- Reference actual team members: Nick, Sam, Ash, Sophie, Tiff, etc.


## Step 6: Strategic Synthesis

**Model:** Opus (highest reasoning capability, worth the cost)
**Input:** ALL JSON from Steps 1-5
**Output:** `data/step6-synthesis.json`

Read `synthesis-prompt.md` for the exact system prompt.

Opus generates:
1. **Creative opportunities** (3-5) connecting dots across data sources
2. **Dependencies** for each opportunity, citing which Step's data supports or gaps
3. **Sequencing** showing which opportunities enable others
4. **Key questions** derived from data gaps identified in Steps 1-5
5. **Confidence scores** with explicit reasoning citing source data
6. **Alerts** (1-3 high-priority items for the hero section)

### Confidence scoring rules
- 80%+ = strong data support from multiple steps, few gaps
- 60-79% = good data support but 1-2 important gaps to validate
- 40-59% = reasonable hypothesis but significant assumptions
- Below 40% = speculative, needs substantial validation on the call

Every score must state: "X% because [cited data supports] but [cited gaps remain]"


## Step 7: HTML Assembly

**Model:** NONE. This is Python.
**Script:** `scripts/assemble_playbook.py`
**Input:** ALL JSON from Steps 1-6
**Output:** Final HTML file

The script reads the JSON files and injects data into the HTML template at `templates/playbook-template.html`. No model generation at this step.

This is the same architecture pattern as RADAR Step 4. See `gotchas/truncation.md` for why this matters.

The script also:
- Calculates the discovery count from actual data
- Validates all counts match
- Generates the source intelligence footer stats
- Sets the phase indicator (1, 2, or 3)
- Stamps the generation date
