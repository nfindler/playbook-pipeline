# Gotcha: Shallow Matching

## The Problem

This is the #1 failure mode for the playbook pipeline. With 2,645+ investors (and growing databases for ICP3-6), a lazy matching approach produces results that look plausible but aren't genuinely good. The client sees 10 investor names they've never heard of, can't verify the match quality, and loses trust in the entire playbook.

Shallow matching looks like:
- One SQL query with `WHERE sector LIKE '%keyword%'` that returns 20 results
- Picking the top 10 by whatever sort order the DB uses
- Writing generic thesis descriptions based on the fund name ("X Ventures invests in clean technology")
- Marking intro paths as "network" without checking HubSpot for a specific person
- Not checking if the fund is still active, fully deployed, or has relevant portfolio conflicts

## Why It Happens

The model defaults to efficiency. One query, rank, done. It's the fastest path. But speed doesn't matter when accuracy does. A playbook that takes 12 minutes with thorough matching is infinitely more valuable than one that takes 5 minutes with shallow matching.

## The Fix: Multi-Pass Architecture

See `references/investor-scoring.md` for the complete methodology. The key principles:

### 1. Cast a WIDE net across 5 different matching dimensions
Every investor should have 5 chances to be found: direct sector, stage+geography, adjacent sector, impact thesis, and relationship-first. An investor missed by one pass might be caught by another. The merge reveals multi-dimensional matches that are almost always the strongest.

### 2. Score RUTHLESSLY after the wide net
The wide net might surface 80-200 candidates from 2,645. The weighted scoring formula then ranks them across 6 factors. The scoring is where you narrow from 200 to 15. Don't narrow with the query. Narrow with the score.

### 3. Web-verify the top 15, not just the top 10
Web verification will disqualify some matches (fund closed, thesis shifted, portfolio conflict). Starting with 15 gives buffer. Any match that survives all 5 passes AND web verification AND scores above 55 is genuinely worth the client's attention.

### 4. Log everything for improvement
Which passes found which investors. What the score distribution looks like. Which matches were disqualified during web verification. Over time, this data shows which passes are most productive and where the DB needs enrichment.

## Red Flags That Matching Is Too Shallow

- All 10 investors are from the same pass (no multi-dimensional coverage)
- No investors have intro paths above "cold" (relationship pass was skipped or HubSpot wasn't queried)
- All thesis summaries sound similar (model generated them from fund names rather than verifying)
- No portfolio conflicts flagged (conflict check was skipped, not that there are no conflicts)
- Score distribution is flat (all between 70-80 means the scoring isn't differentiating)
- No investors from the adjacent sector or impact thesis passes (the creative matching was skipped)

## This Pattern Replicates

The same multi-pass + scoring + verification pattern applies to:
- ICP3 buyer matching (2,000+ contacts)
- ICP4 indigenous community matching
- ICP5 expert matching (smaller DB but same rigor needed)
- ICP6 government contact matching

Get it right for ICP2 first. Then replicate the pattern with adjusted dimensions and weights for each ICP type. See the "Replicable Architecture" section in `investor-scoring.md`.
