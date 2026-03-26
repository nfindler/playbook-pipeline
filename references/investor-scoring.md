# Investor Matching & Scoring Reference (Step 2)

This is the most important step in the pipeline. A bad investor match destroys the playbook's credibility. This methodology is designed to be THOROUGH across 2,645+ records and REPLICABLE as the template for ICP3 (buyers), ICP4 (indigenous), ICP5 (experts), and ICP6 (government) matching.

## Core Principle

The score is NOT "how good is this investor." The score is "how likely is this match to result in a productive conversation within 30 days." A $10B fund with the perfect thesis but zero intro path scores lower than a $50M fund with a warm intro and active deployment.

## Why Simple Queries Fail at 2,645 Records

A naive approach queries `WHERE sector LIKE '%circular%' AND stage = 'Seed'` and gets 30 results. But it misses:
- The healthcare-focused fund that just expanded into circular economy (thesis mismatch in DB, but real-world fit)
- The generalist fund where one partner has a personal interest in the sub-sector (not tagged at the fund level)
- The fund that invested in a competitor and might want exposure to an alternative (portfolio-driven fit)
- The impact fund that doesn't tag by sector but by outcome type (GHG reduction, waste diversion)
- The family office with no website but a warm intro through a ClimateDoor conference relationship

Every missed match is a lost opportunity for the client. The matching must cast a WIDE net, then SCORE ruthlessly.

---

## Multi-Pass Matching Architecture

The matching runs 5 passes against the full database. Each pass uses a different matching dimension. Records found in multiple passes get a "multi-dimensional match" bonus. Records found in only one pass still get scored, they just start from a lower base.

### Pass 1: Direct Sector Match
```sql
SELECT * FROM investors 
WHERE sector_tags LIKE '%{primary_sector}%'
   OR sector_tags LIKE '%{climate_sector_type_1}%'
   OR sector_tags LIKE '%{climate_sector_type_2}%'
   OR sector_tags LIKE '%{climate_sector_type_3}%'
```
This catches investors whose tagged thesis directly matches the company's sector classification. This is the obvious pass, and it's necessary but insufficient.

### Pass 2: Stage + Geography Match (regardless of sector)
```sql
SELECT * FROM investors 
WHERE stage_range LIKE '%{venture_stage}%'
  AND (geography LIKE '%{country}%' OR geography LIKE '%Global%')
  AND last_active > date('now', '-24 months')
```
This catches active investors in the right stage and geography who might have a broader thesis than their sector tags suggest. A generalist Seed fund in Canada that's been active in the last 2 years is worth evaluating even if their tags don't say "Circular Economy."

### Pass 3: Adjacent Sector Match
For every primary sector, there are 2-3 adjacent sectors where investor interest overlaps. Map these:

| Primary Sector | Adjacent Sectors |
|---|---|
| Circular Economy | Clean Industry / Advanced Manufacturing, Sustainable Packaging, Green Construction |
| Ag & Food | Nature-based & Community Solutions, Water & Decontamination |
| Energy & Storage | Clean Industry, Transportation, Buildings & Smart Cities |
| Buildings & Smart Cities | Energy & Storage, Climate Intelligence & Software |
| Carbon | Nature-based & Community Solutions, Energy & Storage |
| Transportation | Energy & Storage, Climate Intelligence & Software |
| Water & Decontamination | Nature-based & Community Solutions, Ag & Food |
| Clean Industry / Advanced Manufacturing | Circular Economy, Energy & Storage |
| Climate Intelligence & Software | All sectors (horizontal play) |
| Nature-based & Community Solutions | Ag & Food, Water & Decontamination, Carbon |
| Critical Minerals / Mining | Clean Industry, Energy & Storage |

```sql
SELECT * FROM investors 
WHERE sector_tags LIKE '%{adjacent_sector_1}%'
   OR sector_tags LIKE '%{adjacent_sector_2}%'
   OR sector_tags LIKE '%{adjacent_sector_3}%'
```

### Pass 4: Impact Thesis Match
Some investors don't organize by sector. They organize by outcome: GHG reduction, waste diversion, resource efficiency, social impact, SDG alignment. Map the company's impact profile to these outcome-based theses.

```sql
SELECT * FROM investors 
WHERE thesis_tags LIKE '%impact%'
   OR thesis_tags LIKE '%climate%'
   OR thesis_tags LIKE '%circular%'
   OR thesis_tags LIKE '%sustainability%'
   OR investor_type LIKE '%Impact%'
   OR investor_type LIKE '%ESG%'
```

Then Sonnet evaluates: "Does this investor's impact thesis logically cover a company that reduces healthcare waste by 82% through reusable sterilization packaging?"

### Pass 5: Relationship-First Match
Query HubSpot for investors where ClimateDoor has the STRONGEST relationships, regardless of sector fit:

```sql
SELECT * FROM investors 
WHERE intro_path_type = 'warm'
   OR intro_path_type = 'network'
ORDER BY last_interaction DESC
LIMIT 50
```

A warm intro to a generalist fund is often more valuable than a cold pitch to a perfectly aligned specialist. This pass catches those. Sonnet then evaluates whether the generalist fund's portfolio has any adjacent plays that make the pitch credible.

---

## De-duplication and Multi-Dimensional Scoring

After all 5 passes, merge the results. An investor found in 3+ passes is almost certainly a strong match. An investor found in 1 pass might be a hidden gem or might be noise.

```python
# Pseudocode for multi-pass merge
all_matches = {}
for pass_name, results in passes.items():
    for investor in results:
        if investor.id not in all_matches:
            all_matches[investor.id] = {
                'investor': investor,
                'found_in_passes': [pass_name],
                'pass_count': 1
            }
        else:
            all_matches[investor.id]['found_in_passes'].append(pass_name)
            all_matches[investor.id]['pass_count'] += 1

# Multi-dimensional match bonus
for match in all_matches.values():
    match['multi_dim_bonus'] = min(match['pass_count'] * 5, 15)  # +5 per pass, max +15
```

---

## Weighted Composite Formula

After the multi-pass merge produces a candidate pool (typically 80-200 investors from 2,645), score each one:

```
TOTAL_SCORE = (thesis_fit * 0.25) + (stage_fit * 0.20) + (geo_fit * 0.10) + (intro_warmth * 0.25) + (fund_activity * 0.10) + (portfolio_signal * 0.10) + multi_dim_bonus
```

Note: intro_warmth is weighted equal to thesis_fit. This is intentional. A warm intro to a 70% thesis fit fund converts better than a cold email to a 95% thesis fit fund.

### Factor 1: Thesis Fit (25%)

How well does the investor's stated thesis align with the company's sector and product?

| Score | Criteria |
|---|---|
| 90-100 | Investor has explicit thesis in this exact sub-sector AND has made 2+ investments in the space in the last 24 months |
| 75-89 | Investor has thesis in the primary sector with adjacent sub-sector investments |
| 60-74 | Investor has broad climate/impact thesis that logically includes this sector |
| 40-59 | Investor is generalist but has made 1+ climate investments ever |
| 20-39 | No visible thesis alignment, but found via relationship or adjacent pass |
| 0-19 | No alignment, noise from broad query |

**How to evaluate (not just tag-match):**
- Read the investor's "About" or thesis statement from their fund page
- Check their portfolio companies: are any in the same or adjacent space?
- Check if any partners have published content about the relevant sector
- Check conference attendance overlap with the company's sector events

### Factor 2: Stage Fit (20%)

Does the investor's check size and stage preference match the company's current raise?

| Score | Criteria |
|---|---|
| 90-100 | Company's raise is in the sweet spot of investor's range (middle third) |
| 75-89 | Company's raise is within investor's stated range |
| 60-74 | Slightly outside range but investor has shown flexibility (made deals outside stated range) |
| 40-59 | Adjacent stage (investor does Series A, company is late Seed) |
| 0-39 | Clear mismatch |

### Factor 3: Geography Fit (10%)

| Score | Criteria |
|---|---|
| 90-100 | Investor has portfolio companies in the same city/province |
| 75-89 | Investor explicitly covers the country |
| 60-74 | Global with no geographic restrictions |
| 40-59 | Global but prefers other regions |
| 0-39 | Geographic restrictions that exclude |

### Factor 4: Intro Warmth (25%)

This is the most important factor for conversion probability.

| Score | Criteria | Intro Path Type |
|---|---|---|
| 95-100 | ClimateDoor has direct GP/partner relationship, interacted in last 3 months | **Direct warm** |
| 85-94 | Direct relationship, interacted in last 6 months | **Warm** |
| 70-84 | Relationship with someone who can make a named intro | **Network** |
| 55-69 | Shared conference attendance in last 2 years, can reference specific event | **Conference** |
| 40-54 | Co-investor overlap (fund has co-invested with a ClimateDoor network fund) | **Co-investor** |
| 25-39 | No intro path, but investor is publicly accessible and actively looking | **Cold qualified** |
| 0-24 | No intro path, investor is hard to reach | **Cold** |

**CRITICAL: Intro path detail must be SPECIFIC:**
- "Via [Name] at [Organization], who co-invested with [Fund] in [Deal]" (not "via network")
- "Met at GLOBE 2024 in Vancouver, [Name] attended the circular economy panel" (not "conference overlap")
- "Direct: Nick spoke with [GP Name] at [Event] in [Month Year]" (not "warm relationship")

HubSpot is the source of truth for intro warmth. If HubSpot doesn't show the relationship, the intro path doesn't exist.

### Factor 5: Fund Activity (10%)

| Score | Criteria |
|---|---|
| 90-100 | New fund/vehicle raised in last 12 months AND 2+ deals in last 6 months |
| 75-89 | 1+ deals in last 6 months |
| 60-74 | Deals in last 12 months, pace slowing |
| 40-59 | Last deal 12-24 months ago |
| 0-39 | No deals in 24+ months or known fully deployed |

### Factor 6: Portfolio Signal (10%)

Does the investor's existing portfolio create a strategic reason to invest?

| Score | Criteria |
|---|---|
| 90-100 | Portfolio company is a direct potential customer, partner, or acquirer of the target company |
| 75-89 | Portfolio company is in an adjacent space that creates synergy |
| 60-74 | Portfolio includes 1+ companies in the same broad sector |
| 40-59 | No portfolio overlap but no conflicts either |
| 0-39 | Portfolio includes a direct competitor (potential conflict) |

**Conflict check is mandatory.** If the investor has a portfolio company that directly competes with the target, flag it prominently. Don't exclude automatically (some investors take multiple bets in a sector) but the playbook must note it.

---

## Scoring Output: Top 10-15

After scoring all candidates, select the top 10-15 (not just top 10). The extra 5 serve as backup if some matches are disqualified during web verification.

### Web Verification (for each top match)

For every investor in the top 15, Sonnet runs a web search to verify:

1. **Is the fund still active?** Check for deals in last 12 months. If no recent activity, check for fund closure announcements.
2. **Deployment status?** Actively investing, partially deployed, fully deployed, raising next fund.
3. **Thesis evolution?** Has the thesis shifted since the DB was last updated? Check recent blog posts, interviews, conference talks.
4. **Partner assignments?** Which partner covers the relevant sector? The intro should target that specific person.
5. **Portfolio conflicts?** Any recent investments in direct competitors?
6. **Recent exits?** An investor who just had a big exit in an adjacent space might be looking to double down.

### Web Verification Can Change Scores

If web verification reveals:
- Fund is fully deployed: drop fund_activity to 0, may drop below threshold
- Thesis has shifted away: reduce thesis_fit
- New portfolio conflict: reduce portfolio_signal, add conflict flag
- Partner recently published about the sector: boost thesis_fit
- Fund just closed new vehicle: boost fund_activity to 90+

### Disqualification Criteria (remove from top 10)

- Fund has been inactive for 24+ months with no new vehicle announced
- Fund website is down or domain expired
- Fund has a direct portfolio competitor AND has stated "one bet per sector" policy
- The DB record is clearly outdated (person has left the fund per LinkedIn)
- The investor is in a geography that cannot legally invest in the company's jurisdiction

---

## Action Level Classification

| Total Score | Level | Display | Playbook Behavior |
|---|---|---|---|
| 85+ | ACT NOW | Teal badge | Lead the playbook with this match. Include in hero alert if score is highest. |
| 70-84 | KNOW | Peach badge | Include in strategy card top matches. Prominent position. |
| 55-69 | WATCH | Steel badge | Include in investor tab but not strategy card. Worth tracking. |
| Below 55 | Exclude | N/A | Don't include. Not worth the client's attention in Phase 1. |

---

## Raise Architecture Generation

After scoring, generate a recommended raise architecture:

1. **Identify anchor:** Highest score with largest check size and strongest intro path
2. **Identify follows:** Score 70+ with complementary check sizes that sum to the target raise
3. **Identify non-dilutive parallel:** From Step 3 grants, which programs run parallel to the raise
4. **Propose structure:** "$[amount] [stage] with [anchor] lead ($[X]) + [follow-on names] ($[Y]) + [non-dilutive program] ($[Z])"
5. **Timeline:** Week-by-week milestones from first intro to target term sheet

---

## Replicable Architecture for Other ICPs

This multi-pass + weighted scoring pattern is designed to replicate across ICPs:

### ICP3 (Buyer Matching)
- Pass 1: Direct sector match (buyer's industry = company's sectors served)
- Pass 2: Procurement type match (buyer actively procuring in relevant category)
- Pass 3: Adjacent sector (buyer in related industry that could use the tech)
- Pass 4: Sustainability mandate match (buyer has published ESG/Scope 3 targets)
- Pass 5: Relationship-first (strongest HubSpot relationships regardless of sector)
- Scoring: Replace thesis_fit with procurement_fit, fund_activity with budget_cycle

### ICP4 (Indigenous Community Matching)
- Pass 1: Geography match (community in same region as company operations)
- Pass 2: Need match (community has published need that company's tech addresses)
- Pass 3: Grant pathway match (indigenous-specific grants that fund the technology)
- Pass 4: Existing relationship (Tiff's relationships with specific communities)
- Pass 5: Economic development priority (community's economic development plan mentions the sector)

### ICP5 (Expert Matching)
- Pass 1: Sector expertise match
- Pass 2: Customer expertise match (expert knows the buyer the company targets)
- Pass 3: Geographic expertise match
- Pass 4: Functional expertise match (capital strategy, BD, grant writing)
- Pass 5: Relationship strength (most engaged experts in the network)

### ICP6 (Government Contact Matching)
- Pass 1: Department/program match (NRCan for energy, ISED for innovation, etc.)
- Pass 2: Regional match (provincial contacts for company's province)
- Pass 3: Program match (contacts at specific grant programs from Step 3)
- Pass 4: Procurement match (contacts in procurement roles for buyer segments from Step 4)
- Pass 5: Relationship-first (strongest government relationships)

---

## Validation Rules

1. Every investor name must exist in the SQLite DB (db_id required) OR be verified via web with fund page URL
2. Every fund name must have a confirmable web presence
3. Intro paths marked "warm" or "network" must reference a specific HubSpot contact with name
4. Check sizes must come from DB or be verified via web search
5. Thesis summaries must cite verifiable sources (fund website, blog, interviews), not inferred from portfolio alone
6. Portfolio conflicts must be explicitly checked and flagged
7. No investor should appear in the playbook if their fund hasn't had activity in 24+ months unless they're raising a new vehicle
8. The multi-pass approach must be logged: which passes found each investor, to help improve matching over time

## Monitoring and Improvement

After each playbook generation, log:
- Total records queried per pass
- Overlap between passes (how many investors found in 2+ passes)
- Score distribution of top 15 (are scores clustered or spread?)
- Web verification outcomes (how many top 15 were disqualified and why)
- Client feedback from Call 1 (did they know any of these investors? Were any matches surprising or off-base?)

This feedback loop is how the matching gets better over time. Every playbook is training data for the next one.
