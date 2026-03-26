---
name: playbook-generator
description: Generate a Growth Playbook page for a climate venture client. Triggers when asked to create a playbook, generate client intelligence, build a pre-call briefing, prepare for a client meeting, research a climate company, or evolve an existing playbook from Phase 1 to 2 to 3. Runs a 7-step pipeline (company research, investor matching, grant scanning, market intelligence, expert matching, strategic synthesis, HTML assembly) using data from SQLite databases, Notion grant DB, HubSpot CRM, and live web scraping. Use this skill for any playbook generation, evolution, or verification task.
---

# Playbook Generator

Generates a Growth Playbook for a climate venture client. The playbook is ClimateDoor's primary sales and intelligence tool, shown on Call 1 and evolved through Phase 1 (pre-call), Phase 2 (post-call), and Phase 3 (active engagement).

**Read `references/company-evaluation-framework.md` FIRST.** It contains the actual ClimateDoor evaluation methodology from the team. This is how Nick and the team think about companies. The pipeline must think this way too.

## The One Rule That Matters

**Every factual claim needs a source.** If you cannot find a source for a claim, mark it as `"verified": false` in the JSON output. The HTML template will display unverified claims with different styling. Never silently present generated information as fact.

## Skill Folder Structure

```
playbook-skill/
  SKILL.md                                    <- You are here
  references/
    company-evaluation-framework.md           <- HOW ClimateDoor evaluates companies (read first)
    pipeline-steps.md                         <- Full 7-step pipeline specification with JSON schemas
    icp-tagging.md                            <- ICP v7 picklist values and matching rules
    investor-scoring.md                       <- Weighted composite scoring formula
    grant-db.md                               <- Notion grant database schema and query patterns
    market-research-rules.md                  <- Sourcing requirements for market data
    synthesis-prompt.md                       <- Exact system prompt for Opus Step 6
    data-sources.md                           <- File paths, DB locations, API endpoints
    playbook-evolution.md                     <- 4-phase evolution system (refine, post-call, deep dive)
  scripts/
    assemble_playbook.py                      <- Step 7: Python HTML assembly (no model)
    validate_playbook.py                      <- Post-generation quality gate
  templates/
    playbook-template.html                    <- v7 design with data injection slots (TODO)
  gotchas/
    truncation.md                             <- RADAR Step 4 pattern: never re-emit large JSON
    fabricated-entities.md                     <- Validation checklist for invented names
    picklist-hallucination.md                 <- DEBRIEF fix: explicit picklist + validation
    grant-staleness.md                        <- Never cache grant deadlines or amounts
```

## Pipeline Overview

| Step | Model | Purpose | Cost | Key Reference |
|------|-------|---------|------|---------------|
| 1 | Haiku | Company research (web scrape + structure) | ~$0.15 | `pipeline-steps.md` |
| 2 | Sonnet | Investor matching (5-pass query + scoring + web verify) | ~$0.50 | `investor-scoring.md`, `icp-tagging.md` |
| 3 | Haiku+Sonnet | Grant scanning (Notion DB + web verification) | ~$0.15 | `grant-db.md` |
| 4 | Sonnet | Market intelligence (sourced signals + buyers) | ~$0.30 | `market-research-rules.md` |
| 5 | Sonnet | Expert matching (SQLite + LinkedIn enrichment) | ~$0.20 | `data-sources.md` |
| 6 | Opus | Strategic synthesis (creative opportunities) | ~$1.50 | `synthesis-prompt.md`, `company-evaluation-framework.md` |
| 7 | Python | HTML assembly (template injection, no model) | ~$0.00 | `assemble_playbook.py` |

Total: ~$2.80/playbook. Runtime: ~10-12 minutes.

## Before You Start

1. You need: a company name and optionally a website URL
2. Read `references/company-evaluation-framework.md` for the evaluation methodology
3. Check that the investor SQLite DB is accessible (path in `references/data-sources.md`)
4. Check that the Notion grant DB is connected (database ID in `references/grant-db.md`)
5. Check `references/icp-tagging.md` for current ICP picklist values
6. For Phase 2+, you also need: Fireflies transcript or DEBRIEF extraction output

## Execution Flow

### Step 1: Company Research (Haiku)
Scrape and structure company data with source URLs on every claim.
- Read `references/pipeline-steps.md` for the full output JSON schema
- Key outputs: company profile, product claims, funding history, regulatory status, team, news signals, traction (logos on website), data gaps
- Every factual claim gets a `source_url` field. No exceptions.

### Step 2: Investor Matching (Sonnet)
Query the investor SQLite database (2,645+ contacts) using MULTI-PASS matching: 5 separate query passes (direct sector, stage+geography, adjacent sector, impact thesis, relationship-first), merge and de-duplicate, apply 6-factor weighted scoring, web-verify top 15, disqualify stale/conflicted funds, output top 10.
- Read `references/investor-scoring.md` for the complete multi-pass methodology
- Read `references/icp-tagging.md` for matching rules and picklist values
- Read `gotchas/shallow-matching.md` for why single-query matching fails
- CRITICAL: Every investor name must come from the database. See `gotchas/fabricated-entities.md`
- Intro paths must reference specific HubSpot contacts by name
- This multi-pass pattern is the TEMPLATE for ICP3, ICP4, ICP5, ICP6 matching

### Step 3: Grant Scanning (Haiku + Sonnet)
Query the Notion grant database (Layer 1), web-verify current details (Layer 2), discover new programs (Layer 3).
- Read `references/grant-db.md` for the Notion schema, query patterns, and two-layer architecture
- Read `gotchas/grant-staleness.md` for the staleness prevention pattern
- Dollar amounts and deadlines MUST come from web scraping the program's official page
- Flag any program whose page can't be reached as "unverified"

### Step 4: Market Intelligence (Sonnet)
Web research for buyer segments, market signals, competitive landscape, conference targets.
- Read `references/market-research-rules.md` for sourcing requirements
- EVERY market sizing number needs a cited source OR shown calculation methodology
- Sector temperature assessment using current news (from Step 1 signals)

### Step 5: Expert Matching (Sonnet)
Query the expert SQLite database (28 contacts), match by sector/capability/geography, enrich with LinkedIn.
- Bios come from the database or LinkedIn, NEVER generated
- Agreement status from HubSpot (signed, pending, prospective)
- Also match the ClimateDoor internal team (Growth Pod): Nick, Sam, Ash, Sophie, Tiff

### Step 6: Strategic Synthesis (Opus)
The brain. Receives ALL JSON from Steps 1-5. Generates creative opportunities, dependencies, sequencing, key questions, confidence scores.
- Read `references/synthesis-prompt.md` for the exact system prompt
- Read `references/company-evaluation-framework.md` for the thinking methodology
- MUST include at least one "unique angle" (geographic, national security, grants-as-BD, sector temperature)
- MUST check grants-as-BD-tool pattern for every company
- MUST check Indigenous community angles (ICP4) for every company
- Dependencies MUST link to Key Questions
- Confidence scores MUST cite which Step's data supports or creates gaps

### Step 7: HTML Assembly (Python)
**CRITICAL: This step is Python template injection, NOT model generation.**
- Run `scripts/assemble_playbook.py`
- Never ask the model to re-emit structured JSON as HTML
- See `gotchas/truncation.md` for why

### Post-Generation: Verification
Run `scripts/validate_playbook.py` to catch:
1. Fabricated investor names not in the database
2. Grant program URLs that don't resolve
3. Discovery count math errors
4. Missing confidence score reasoning
5. Picklist values outside valid sets
6. Market sizing numbers without sources
7. Missing unique angles (the playbook feels generic)
8. Orphan dependencies (dependency has no matching Key Question)

## Phase Evolution

### Phase 1 (Pre-Call)
Generated entirely from web research + database matching. No client input. This is the "we did this before we even talked to you" moment. Every claim is either sourced from the web or from ClimateDoor's internal databases.

### Phase 2 (Post-Call)
Input: Fireflies transcript or DEBRIEF extraction output.
The model re-runs Steps 2-6 with additional context from the call:
- Investor matches re-scored based on confirmed priorities
- Grant opportunities filtered by confirmed eligibility
- Opportunities re-ranked by client-confirmed interest
- Key Questions replaced with confirmed answers + new deeper questions
- New opportunities may emerge from call insights

### Phase 3 (Active Engagement)
Input: Ongoing call notes, pipeline updates, milestone completions.
The playbook becomes a living document:
- Investor statuses update (intro sent, meeting scheduled, term sheet received)
- Grant applications track (submitted, under review, approved)
- Buyer pipeline shows actual outreach results
- Opportunity confidence scores adjust based on real-world feedback

## Output

Final output is a standalone HTML file deployed to `climatedoor.ai/playbooks/[company-slug]/`.
The HTML template uses the v7 design system with:
- Warm canvas background (#FAFAF7), Montserrat font, ClimateDoor brand colors
- Animated dot network hero with phase indicators
- Tabbed sections (Playbook, Investors, Buyers, Experts, Grants, Landscape)
- Playbook tab flow: Strategy Pillars, Creative Opportunities, Key Questions, Competitive Position
- Expandable cards with hover states, bold key terms, peach dot markers
- DTI-pattern investor cards with score rings
- Opportunity cards with two-column layout (narrative+deps left, metrics+timeline right)
- Scroll-triggered animations, animated counters, responsive design

## Critical Gotchas (read all of these)

1. **Shallow matching** (`gotchas/shallow-matching.md`): The #1 failure mode. A single SQL query across 2,645 investors produces plausible but mediocre matches. The fix is multi-pass matching: 5 query passes across different dimensions, merge, score with the 6-factor weighted formula, web-verify the top 15, disqualify stale/conflicted funds. This pattern replicates across ICP3-6.
2. **Fabricated entities** (`gotchas/fabricated-entities.md`): The model invents investor names. Every name must come from the DB or be web-verified.
3. **Picklist hallucination** (`gotchas/picklist-hallucination.md`): Explicit picklist in system prompt + post-extraction validation function.
4. **Truncation** (`gotchas/truncation.md`): Never re-emit large JSON through a model. Step 7 is Python.
5. **Grant staleness** (`gotchas/grant-staleness.md`): Dollar amounts and deadlines must be web-scraped at generation time.
6. **Market sizing fabrication**: Every number needs a source or shown math. "$80M+" with no methodology is not acceptable.
7. **Discovery count must be traceable**: Total = sum of individual counts. Show the breakdown. The client will check.
