# Template Slot Reference

Maps every `{{SLOT}}` in `playbook-template.html` to its data source and assembly script function.

## Simple Value Slots (string replacement)

| Slot | Data Source | Example Value |
|---|---|---|
| `{{COMPANY_NAME}}` | Step 1: `company.name` | "Frett Solutions" |
| `{{HERO_COMPANY_FIRST}}` | Split from company name | "Frett" |
| `{{HERO_COMPANY_LAST}}` | Split from company name | "Solutions" |
| `{{COMPANY_DESCRIPTION}}` | Step 1: `company.description` | "Reusable PFAS-free textile sterilization pouches..." |
| `{{HERO_TAGS}}` | Step 1: stage, TRL, sector, geography | `<span class="htg htg-s">Seed</span><span class="htg htg-s">TRL 8</span>...` |
| `{{PHASE}}` | Pipeline parameter | "1" or "2" or "3" |
| `{{PREPARED_FOR}}` | Pipeline parameter (CD rep name) | "Nick Findler" |
| `{{GENERATION_DATE}}` | Runtime | "March 19, 2026" |
| `{{DISCOVERY_TOTAL}}` | Calculated sum of all counts | 33 |

## Count Slots (integers, used in hero counters)

| Slot | Data Source | Calculation |
|---|---|---|
| `{{COUNT_INVESTORS}}` | Step 2: `len(investors.matches)` | 10 |
| `{{COUNT_GRANTS}}` | Step 3: `len(grants.programs)` | 4 |
| `{{COUNT_SEGMENTS}}` | Step 4: `len(market.buyer_segments)` | 4 |
| `{{COUNT_SIGNALS}}` | Step 4: `len(market.signals)` | 5 |
| `{{COUNT_OPPORTUNITIES}}` | Step 6: `len(synthesis.creative_opportunities)` | 4 |
| `{{COUNT_EXPERTS}}` | Step 5: `len(experts.matches)` | 3 |
| `{{COUNT_INDIGENOUS}}` | Step 4: `len(market.indigenous_matches)` | 2 |
| `{{COUNT_EVENTS}}` | Step 4: `len(market.conferences)` | 3 |

**DISCOVERY_TOTAL must equal the sum of all COUNT_ slots.** The assembly script validates this.

## Pillar Subtitle Slots (short descriptive text)

| Slot | Data Source | Example |
|---|---|---|
| `{{PILLAR_CAPITAL_SUB}}` | Step 2: generated from top score | "Investor matches scored" |
| `{{PILLAR_GRANTS_SUB}}` | Step 3: generated from pipeline total | "$1.5M+ pipeline mapped" |
| `{{PILLAR_SALES_SUB}}` | Step 4: generated from segment count | "Enterprise buyer segments" |
| `{{PILLAR_SIGNALS_SUB}}` | Step 4: generated from signal count | "Market forces tracked" |

## Footer Stat Slots

| Slot | Data Source | Example |
|---|---|---|
| `{{STAT_INVESTORS_SCANNED}}` | Step 2: total records queried from investor DB | "2,645" |
| `{{STAT_STAGE_MATCH}}` | Step 2: records matching stage filter | "499" |
| `{{STAT_SECTOR_MATCH}}` | Step 2: records matching sector filter | "347" |
| `{{STAT_REGION_MATCH}}` | Step 2: records matching region filter | "388" |

## Block-Level HTML Slots (entire sections built by assembly script)

These are the heavy slots. The assembly script builds complete HTML sections from structured JSON and drops them in.

### `{{ALERTS_HTML}}`
Source: Step 6 `synthesis.alerts[]`
Builds 1-3 alert cards. Each alert has a type (al-h for high priority, al-s for signal) and contains a label + text.

### `{{PLAYBOOK_TAB_CONTENT}}`
Source: Steps 2-6 (all synthesis data)
Builds the entire Playbook tab containing:
1. **Strategy Cards section:** 4 expandable cards (Capital, Grants, Sales, Signals) with detail grids
2. **Creative Opportunities section:** 3-5 expandable opportunity cards with two-column layout (narrative+deps left, metrics+timeline right)
3. **Key Questions section:** 8-15 numbered questions with context paragraphs
4. **Competitive Position section:** Intro + 3 numbered factor cards + risk card

This is the largest and most complex slot. The assembly script has dedicated builder functions for each sub-section.

### `{{OPPORTUNITIES_TAB_CONTENT}}`
Source: N/A (redirect)
Simple redirect message pointing to the Playbook tab. Content is static, not data-driven.

### `{{INVESTORS_TAB_CONTENT}}`
Source: Step 2 `investors.matches[]`
Builds the DTI-pattern investor cards. Each card has:
- Score ring SVG (animated on scroll)
- Name, fund, action level badge
- Expandable detail: thesis narrative, INTRO PATH box, APPROACH box, insight bullets

### `{{BUYERS_TAB_CONTENT}}`
Source: Step 4 `market.buyer_segments[]`
Builds buyer segment cards with expandable details: decision maker, sales cycle, ACV potential, entry strategy.

### `{{EXPERTS_TAB_CONTENT}}`
Source: Step 5 `experts.matches[]` + Growth Pod team
Builds expert cards with bios, "Why [Company]" rationale, and agreement status. Also includes Growth Pod section.

### `{{GRANTS_TAB_CONTENT}}`
Source: Step 3 `grants.programs[]`
Builds grant program cards with eligibility fit, application strategy, timeline, strategic sequencing.

### `{{INDIGENOUS_TAB_CONTENT}}`
Source: Step 4 `market.indigenous_matches[]` + Notion grant DB (ICP4 filtered) + Step 6 synthesis
Builds indigenous partnership cards using the same pattern as investor cards:
- Score ring (community fit score based on tech applicability, grant pathways, geographic proximity, existing CD relationships)
- Community/org name, region, action level badge (ACT NOW / KNOW / WATCH)
- Expandable detail: narrative explaining the partnership opportunity
- INTRO PATH box (Tiff's relationships, conference connections, regional contacts)
- APPROACH box (community-first engagement: understand needs, not pitch product)
- Grant pathway box (specific indigenous grants that fund the deployment, this is the grants-as-BD-tool pattern)

**For Phase 1 (no ICP4 DB yet):** Step 4 does web research to identify indigenous community angles based on the company's technology, geography, and sector. The synthesis prompt (Step 6) checks every company for indigenous applicability. If no fit, the tab shows "No indigenous partnership opportunities identified for this company" rather than being hidden.

**For future (660+ communities mapped):** Multi-pass matching against the ICP4 database, same architecture as investor matching.

### `{{SIGNALS_TAB_CONTENT}}`
Source: Step 4 `market.signals[]` + Step 1 `company.signals.sector_temperature`
Builds time-dated signal cards. Each card has:
- Date (month/year of the signal)
- Headline (specific, not generic: "Canada's Clean Fuel Regulations intensify compliance pressure" not "Regulations tightening")
- Action level badge: ACT NOW (teal, time-sensitive), KNOW (peach, strategic context), WATCH (steel, developing)
- Relevance arrow: One sentence connecting the signal to the specific company's situation
- Source attribution (URL to the regulation, announcement, or report)

Signal cards are sorted by action level (ACT NOW first), then by date (newest first).

### `{{LANDSCAPE_TAB_CONTENT}}`
Source: Step 4 `market.competitors[]` (or placeholder for Phase 1)
In Phase 1, shows a placeholder message. In Phase 2+, builds competitive landscape with competitor cards.

## Assembly Script Function Map

```python
# Each slot maps to a builder function in assemble_playbook.py:

SLOT_BUILDERS = {
    # Simple value slots
    '{{COMPANY_NAME}}':           lambda d: d['company']['company']['name'],
    '{{HERO_COMPANY_FIRST}}':     lambda d: d['company']['company']['name'].split()[0],
    '{{HERO_COMPANY_LAST}}':      lambda d: ' '.join(d['company']['company']['name'].split()[1:]),
    '{{COMPANY_DESCRIPTION}}':    lambda d: d['company']['company']['description'],
    '{{PHASE}}':                  lambda d, p: str(p),
    '{{GENERATION_DATE}}':        lambda d: datetime.now().strftime('%B %d, %Y'),
    
    # Count slots
    '{{COUNT_INVESTORS}}':        lambda d: str(len(d['investors']['matches'])),
    '{{COUNT_GRANTS}}':           lambda d: str(len(d['grants']['programs'])),
    # ... etc
    
    # Block-level HTML builders
    '{{ALERTS_HTML}}':            build_alerts_html,
    '{{PLAYBOOK_TAB_CONTENT}}':   build_playbook_tab_html,
    '{{INVESTORS_TAB_CONTENT}}':  build_investors_tab_html,
    '{{BUYERS_TAB_CONTENT}}':     build_buyers_tab_html,
    '{{EXPERTS_TAB_CONTENT}}':    build_experts_tab_html,
    '{{GRANTS_TAB_CONTENT}}':     build_grants_tab_html,
    '{{LANDSCAPE_TAB_CONTENT}}':  build_landscape_tab_html,
}
```

## Styling Reference

The template preserves all CSS from the v7 design. Key class patterns for builders:

- Strategy cards: `.sc`, `.sc-cap`, `.sc-gra`, `.sc-sal`, `.sc-mkt`, `.sc-top`, `.sc-det`, `.dg`, `.di`
- Opportunity cards: `.opp`, `.opp-top`, `.opp-detail`, `.opp-cols`, `.opp-deps`, `.opp-seq`, `.opp-vs`, `.opp-metrics`, `.opp-timeline`, `.opp-conf`
- Investor cards: `.inv`, `.inv-top`, `.inv-det`, `.inv-score-ring`, `.inv-badge`
- Questions: `.qi`, `.qn`, `.qt`, `.qc`
- Competitive: `.comp-c`, `.comp-factor`, `.comp-risk`
- Alerts: `.al`, `.al-h` (high), `.al-s` (signal)
- Scroll animations: `.sr` class triggers fade-in on scroll, `.d1`/`.d2`/`.d3`/`.d4` add stagger delays
