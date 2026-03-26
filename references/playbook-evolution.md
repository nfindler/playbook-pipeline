---
name: playbook-evolution
description: Manages the lifecycle of Growth Playbooks through 4 phases. Triggers when creating a new playbook from intake materials, editing/refining an existing playbook, processing post-call transcripts to upgrade a playbook, or running a deep-dive operational playbook for signed clients. Also handles document upload processing, inline section editing, text prompt feedback, version control, and the DEBRIEF integration for transcript-driven evolution.
---

# Playbook Evolution System

A Growth Playbook is not a static document. It evolves through 4 phases, each adding depth, closing data gaps, and increasing confidence scores. This skill manages the full lifecycle.

## Phase Overview

| Phase | Trigger | Cost | Depth | Output |
|---|---|---|---|---|
| 1: Intake | New prospect, docs received | ~$2.80 | Pre-call intelligence | 53+ discoveries, 12 key questions |
| 2: Refine | Team review before presenting | ~$0-2 per edit | Polish and correction | Presentation-ready playbook |
| 3: Post-Call | Fireflies transcript received | ~$5-8 | Enriched with founder data | Closed data gaps, re-scored matches |
| 4: Deep Dive | Client signs contract | ~$15-25 | Full operational playbook | 50+ investors, grant drafts, named contacts |

---

## Phase 1: Intake (Already Built)

See `playbook-skill/SKILL.md` for the complete 7-step pipeline.

**Input:** Company name, website URL, any docs the prospect has shared (deck, one-pager, financial summary), onboarding questionnaire responses.

**Process:** Steps 1-7 run automatically. Total cost ~$2.80, runtime ~12 minutes.

**Output:** Live playbook page at `climatedoor.ai/playbooks/{company-slug}/`

**Key principle:** "They did all this before we even talked?" The playbook exists before Call 1 is scheduled. The 12 Key Questions guide the call. The 53+ discoveries demonstrate ClimateDoor's intelligence capability.

### Document Processing at Intake

When docs are provided at intake (before the pipeline runs), they feed into Step 1:

**Pitch deck (PDF):** Extract company description, team, product details, traction, funding history, market positioning. These fill data gaps that the website alone can't provide.

**Financial summary:** Revenue, burn rate, runway, funding stage. These directly impact investor matching (Step 2) and grant eligibility (Step 3).

**Onboarding questionnaire:** Goals, challenges, current partnerships, geographic focus, ideal customer profile. These shape the synthesis (Step 6) and opportunity generation.

**Processing approach:**
1. Convert uploaded docs to text (PDF extraction, DOCX parsing)
2. Append extracted content to Step 1's web research data
3. Flag doc-sourced claims separately from web-sourced claims (different confidence levels)
4. Step 1 JSON includes a `document_sources` array tracking what was provided

---

## Phase 2: Refine (Build This)

After Phase 1 generates the playbook, the ClimateDoor team reviews it before presenting to the prospect. Phase 2 provides three editing mechanisms:

### 2A: Inline Section Editing

Each section of the playbook has an edit affordance (pencil icon in edit mode). Clicking it opens the section for direct text editing.

**How it works:**
- Playbook URL gets an `/edit` mode: `climatedoor.ai/playbooks/{slug}/edit`
- Edit mode shows pencil icons on every section
- Clicking a pencil opens an inline editor for that section's content
- Save writes the edit directly to the playbook HTML
- Every save creates a version entry in the version log

**What's editable:**
- Company description (hero section)
- Strategy pillar summaries and details
- Opportunity narratives, dependencies, metrics, timelines
- Investor thesis summaries, approach, intro path details
- Buyer segment descriptions, ACV calculations
- Grant program details and eligibility notes
- Signal headlines and relevance text
- Indigenous partnership narratives and approach
- Key questions and context paragraphs
- Competitive position narrative and factors
- Alert text

**What's NOT directly editable (requires re-run):**
- Scores (investor match scores, opportunity confidence, grant fit)
- Discovery counts (derived from data)
- Source Intelligence footer stats (derived from pipeline metadata)

### 2B: Text Prompt Feedback

A chat bar at the bottom of edit mode accepts natural language instructions that modify specific sections.

**How it works:**
1. Team member types a prompt: "Make the capital strategy more aggressive, they told us they want to raise $5M not $2M"
2. System identifies which section(s) the prompt affects (Capital strategy pillar, investor tab, opportunity confidence scores)
3. Sonnet regenerates ONLY the affected sections, preserving everything else
4. The regenerated sections are injected into the playbook
5. Team member reviews the changes, accepts or reverts

**Prompt routing logic:**
- "change the capital strategy" -> regenerate Strategy Pillars: Capital section
- "add an investor" -> regenerate Investors tab (or add a manually specified investor)
- "the founder said they have $2M ARR" -> update Step 1 data, re-run Steps 2-6 for affected sections
- "remove the ESPR opportunity" -> delete the opportunity card, update discovery count
- "the indigenous angle doesn't apply" -> hide Indigenous tab, update counts
- "make the questions sharper" -> regenerate Key Questions section
- "they're actually pre-revenue, not growth stage" -> major change, re-run Steps 2-6

**Cost per prompt edit:** ~$0.10-0.50 depending on scope (single section vs. cascade re-run)

### 2C: Document Upload (Mid-Refinement)

Additional documents can be uploaded during Phase 2 to enrich the playbook.

**How it works:**
1. Team member uploads a document (cap table, customer list, financial model, competitor analysis)
2. System extracts relevant data from the document
3. System identifies which pipeline steps are affected
4. Only the affected steps re-run (not the full pipeline)
5. Step 7 reassembles with the updated data

**Document-to-Step mapping:**
| Document Type | Affects Steps | What Changes |
|---|---|---|
| Cap table / financial model | 2 (investors), 3 (grants), 6 (synthesis) | Investor matching re-scored with real financials, grant eligibility refined |
| Customer list / references | 4 (market), 6 (synthesis) | Named customers validate buyer segments, new signals |
| Competitor analysis | 4 (market), 6 (synthesis) | Competitive position updated, opportunity confidence adjusted |
| Pitch deck (updated version) | 1 (company), then cascade | Company data refreshed, all downstream steps re-evaluated |
| Team bios / org chart | 5 (experts), 6 (synthesis) | Growth Pod assignments updated |
| Patent / IP documentation | 1 (company), 4 (market) | TRL adjusted, competitive moat updated |
| Grant application (in progress) | 3 (grants) | Grant already applied for, adjust recommendations |
| Call notes (informal) | 6 (synthesis) | Data gaps partially closed, questions updated |

### Version Control

Every change creates a version. The version log tracks:
```json
{
  "version_id": "v1.0.0",
  "phase": 1,
  "timestamp": "2026-03-20T04:30:00Z",
  "change_type": "pipeline_generation",
  "changed_by": "system",
  "changes": ["Initial playbook generation from 7-step pipeline"],
  "data_files": {
    "step1": "step1-company-v1.json",
    "step2": "step2-investors-v1.json",
    "step3": "step3-grants-v1.json",
    "step4": "step4-market-v1.json",
    "step5": "step5-experts-v1.json",
    "step6": "step6-synthesis-v1.json"
  }
}
```

Version comparison shows:
- What changed between versions (diff view)
- Which sections were affected
- Who made the change (system vs. team member name)
- Cost of the change (API tokens used)

Roll back is available to any prior version.

---

## Phase 3: Post-Call Upgrade

After Call 1, the Fireflies transcript transforms the playbook from "pre-call intelligence" to "post-call strategy."

### Trigger
Fireflies webhook delivers the transcript to `climatedoor.ai/debrief/api/webhook`, OR the team manually pastes the transcript into DEBRIEF.

### Process

1. **DEBRIEF ICP1 Extraction** (already built):
   - Transcript processed through the DEBRIEF ICP1 extraction engine
   - Structured data extracted: revenue, funding status, team size, customer names, partnerships, challenges, goals
   - Picklist values validated against ICP v7

2. **Data Gap Closure:**
   - Compare DEBRIEF extraction output against Step 1's `data_gaps` array
   - For each data gap that now has an answer, update the Step 1 JSON
   - Log which gaps were closed and which remain

3. **Selective Re-Run:**
   Not all steps need to re-run. Only steps affected by the new data:
   
   | New Data | Re-Run Steps | Why |
   |---|---|---|
   | Revenue / financials revealed | 2, 3, 6 | Investor check sizes recalibrated, grant eligibility refined |
   | Funding stage clarified | 2, 6 | Investor stage matching sharpens |
   | Customer names revealed | 4, 6 | Named customers validate buyer segments |
   | Team size confirmed | 3, 5, 6 | Grant eligibility (IRAP employee limits), team capacity |
   | Geographic expansion plans | 2, 3, 4, 6 | New investor geographies, new grant programs, new buyer markets |
   | Competitive intel from founder | 4, 6 | Competitive position updated |
   | Partnership details | 4, 5, 6 | New buyer channels, expert connections |

4. **Confidence Score Updates:**
   Every confidence score in the playbook gets re-evaluated:
   - Opportunity confidence: Jumps when dependencies are confirmed
   - Investor match scores: Re-weighted with real financial data
   - Grant fit scores: Eligibility confirmed or disconfirmed
   - Overall playbook confidence: Percentage of data gaps closed

5. **New Opportunity Generation:**
   Opus re-runs Step 6 synthesis with enriched data. New opportunities may emerge that weren't visible with pre-call data. Example: founder reveals a government pilot program in progress, which creates a "Government Validation" opportunity that wasn't possible to identify from web research alone.

6. **Question Evolution:**
   The 12 Key Questions from Phase 1 are evaluated:
   - Questions that were answered: Marked as resolved, answer captured
   - Questions that generated new questions: New follow-ups added
   - Unanswered questions: Remain, escalated for Call 2

7. **Step 7 Reassembly:**
   The playbook HTML is regenerated with all updated data. The phase indicator changes from "Phase 1 / Pre-Call Intelligence" to "Phase 2 / Post-Call Strategy."

### Output
- Updated playbook at same URL (versioned, old version preserved)
- "What Changed" summary showing closed gaps, score changes, new opportunities
- Recommended Call 2 agenda based on remaining questions

### Cost: ~$5-8
Higher than Phase 1 because selective re-runs may include Opus for synthesis, and the transcript processing adds Sonnet calls for DEBRIEF extraction.

---

## Phase 4: Deep Dive (Signed Client)

When the client signs, spend the tokens. This playbook becomes the operational document the Growth Pod works from every week.

### Trigger
Client contract signed. Growth Pod assigned.

### What Changes from Phase 3

**Investor Matching: Exhaustive**
- Phase 1-3: Top 20 scored investors
- Phase 4: ALL qualified investors (50-100+) with full Sonnet evaluation on each
- Every investor gets a web-verified thesis summary, not just the top 20
- Named partner at each fund who covers the sector
- HubSpot contact records created/updated for each match
- Intro sequence drafted for top 10 (email templates, LinkedIn messages)

**Grant Applications: Drafted**
- Phase 1-3: 8 programs identified with fit scores
- Phase 4: Top 3-5 grants get full application outline drafted
- Eligibility checklists completed
- Required document lists prepared
- Draft responses to common evaluation criteria
- Sophie reviews and refines before submission

**Buyer Contacts: Named**
- Phase 1-3: Buyer segments with organization names
- Phase 4: Specific contacts pulled from HubSpot with email, phone, title
- Decision maker mapping: who approves procurement at each target organization
- Intro paths mapped through ClimateDoor's network
- Outreach sequence drafted for top 5 buyer targets

**RFP Matching: Activated**
- Phase 4 activates the RFP scanner (see `rfp-skill/SKILL.md`) against the company profile
- Direct RFPs the company can bid on
- Customer RFPs that create demand for the company's product
- Weekly re-scan during engagement

**Competitive Intelligence: Deep**
- Phase 1-3: 3-5 competitors identified
- Phase 4: Full competitive teardown on each
- Pricing comparison where available
- Win/loss analysis from similar deals
- Differentiation positioning for each competitor

**Weekly Evolution:**
- Playbook auto-updates weekly with new signals, RFP matches, and deal progress
- Call transcripts from weekly check-ins feed through DEBRIEF and update the playbook
- Deal pipeline progress (from HubSpot) reflected in opportunity confidence scores
- Grant application status updates
- Investor conversation outcomes (meeting happened, passed, interested) update intro paths

### Cost: ~$15-25 per generation, ~$3-5/week for ongoing evolution
Worth it when the retainer is $10K+/month.

---

## Technical Architecture

### File Structure
```
/home/openclaw/playbook-skill/data/{company-slug}/
  versions/
    v1.0.0/                    # Phase 1 initial generation
      step1-company.json
      step2-investors.json
      step3-grants.json
      step4-market.json
      step5-experts.json
      step6-synthesis.json
      playbook.html
      metadata.json            # Version info, cost, timestamp
    v1.1.0/                    # Phase 2 edit (text prompt)
      step6-synthesis.json     # Only changed files stored
      playbook.html
      metadata.json
    v2.0.0/                    # Phase 3 post-call upgrade
      step1-company.json       # Updated with transcript data
      step2-investors.json     # Re-scored
      step6-synthesis.json     # Re-synthesized
      playbook.html
      metadata.json
    v3.0.0/                    # Phase 4 deep dive
      ...all files, exhaustive versions...
  current/                     # Symlink to latest version
    playbook.html              # Currently deployed
  uploads/                     # Documents uploaded during refinement
    pitch-deck-v2.pdf
    cap-table.xlsx
    call1-transcript.json      # From Fireflies/DEBRIEF
  edit-log.json                # All edits with timestamps and authors
```

### Edit Mode Architecture

The edit mode (`/edit` URL) is a thin React layer on top of the playbook HTML:

```
climatedoor.ai/playbooks/{slug}/        -> Static playbook (presentation mode)
climatedoor.ai/playbooks/{slug}/edit    -> Edit mode (team only, authenticated)
```

**Edit mode components:**
1. **Section editors:** Click-to-edit on any text section. Rich text for narratives, structured form for scores/metrics.
2. **Prompt bar:** Chat input at bottom. Natural language instructions routed to affected sections.
3. **Document upload:** Drag-and-drop zone. Uploaded files processed and routed to relevant steps.
4. **Version sidebar:** Shows version history, allows comparison and rollback.
5. **Change indicator:** Badge on each section showing if it's been edited from the pipeline-generated version.

**Authentication:** Edit mode requires ClimateDoor team authentication. The presentation mode URL is shareable with clients (no edit affordances visible).

### API Endpoints (Node.js proxy, port 4300)

```
POST /api/playbooks/{slug}/edit
  Body: { section: "capital_pillar", content: "new text" }
  -> Inline edit, save to current version

POST /api/playbooks/{slug}/prompt
  Body: { prompt: "make capital strategy more aggressive", context: "they want $5M" }
  -> Sonnet processes prompt, returns affected sections, applies changes

POST /api/playbooks/{slug}/upload
  Body: multipart form with document
  -> Extract data, identify affected steps, selective re-run

POST /api/playbooks/{slug}/evolve
  Body: { transcript_id: "fireflies-xxx" } or { transcript_text: "..." }
  -> Full Phase 3 evolution

POST /api/playbooks/{slug}/deep-dive
  Body: { config: { investors: "exhaustive", grants: "draft", buyers: "named" } }
  -> Phase 4 deep dive generation

GET /api/playbooks/{slug}/versions
  -> List all versions with metadata

POST /api/playbooks/{slug}/rollback
  Body: { version: "v1.0.0" }
  -> Restore a previous version
```

### Deployment

Edit mode served from the same Caddy route as the playbook, with path detection:
```
handle /playbooks/{slug}/edit {
  # Serve edit mode React app (authenticated)
  root * /var/www/climatedoor/playbook-editor
  try_files {path} /index.html
  file_server
}

handle /playbooks/{slug}/* {
  # Existing static playbook serving
  root * /var/www/climatedoor/playbooks
  ...
}
```

The Node.js proxy (port 4300) handles all edit/evolve API calls, managed by PM2.

---

## The 100X Compounding Effect

Every playbook generated enriches the system:

1. **Investor matching improves:** When FTQ actually takes a meeting with Frett Design, that validates the matching algorithm. The next circular economy company gets FTQ ranked even higher.

2. **Grant database grows:** Every new grant program discovered during a playbook generation gets added to the Notion database. Sophie confirms and enriches it. The 50th playbook has 3x the grant coverage of the 1st.

3. **Buyer segments cross-pollinate:** DSOs identified for Frett Design are also relevant to the next healthcare company. The buyer intelligence compounds.

4. **Conference relationships deepen:** Every intro path that actually works gets validated. The warm intro network gets more reliable over time.

5. **Competitive intelligence accumulates:** Competitor data from one client's playbook informs another client's positioning. The competitive landscape gets richer.

6. **Question patterns emerge:** After 20 playbooks, you know the 5 questions that ALWAYS matter for Series A climate companies. The synthesis gets sharper.

7. **The ICP tagging system evolves:** Every company through the pipeline reveals edge cases in the tagging system. The 95 cross-matching rules grow to 150.

No competitor can replicate this because the data moat requires:
- 2,645+ investor records with warmth scores from 5 years of conferences
- 660+ indigenous community mapping
- Live Notion grant database maintained by Sophie
- ICP v7 tagging system with 95 cross-matching rules
- 5 years of conference relationships baked into HubSpot
- The DEBRIEF extraction engine turning every call into structured data
- The pipeline itself, encoding ClimateDoor's evaluation methodology into code

The pipeline is the engine. The data is the moat. The playbook is the product. Together, they compound.
