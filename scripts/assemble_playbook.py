#!/usr/bin/env python3
"""
Playbook HTML Assembly Script (Step 7)

Reads structured JSON from Steps 1-6 and injects data into the HTML template.
NO MODEL GENERATION happens at this step. This is pure Python template injection.

This is the same architecture pattern as RADAR Step 4.
See gotchas/truncation.md for why the model must never re-emit large structured data.

Usage:
    python assemble_playbook.py --company-slug frett-design --phase 1
    python assemble_playbook.py --company-slug frett-design --phase 2 --transcript call-notes.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'templates', 'playbook-template.html')
DATA_DIR = '/home/claude/playbook-data'
OUTPUT_DIR = '/var/www/climatedoor/playbooks'


def load_step_data(company_slug):
    """Load all JSON outputs from pipeline steps 1-6."""
    base = os.path.join(DATA_DIR, company_slug)
    data = {}
    
    step_files = {
        'company': 'step1-company.json',
        'investors': 'step2-investors.json',
        'grants': 'step3-grants.json',
        'market': 'step4-market.json',
        'experts': 'step5-experts.json',
        'synthesis': 'step6-synthesis.json',
    }
    
    for key, filename in step_files.items():
        filepath = os.path.join(base, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data[key] = json.load(f)
        else:
            print(f"WARNING: Missing {filepath}")
            data[key] = None
    
    return data


def calculate_discovery_count(data):
    """
    Calculate total discoveries from actual data.
    The count must be traceable: sum of individual counts.
    """
    counts = {
        'investors': len(data.get('investors', {}).get('matches', [])),
        'grants': len(data.get('grants', {}).get('programs', [])),
        'buyer_segments': len(data.get('market', {}).get('buyer_segments', [])),
        'market_signals': len(data.get('market', {}).get('signals', [])),
        'opportunities': len(data.get('synthesis', {}).get('creative_opportunities', [])),
        'experts': len(data.get('experts', {}).get('matches', [])),
        'conferences': len(data.get('market', {}).get('conferences', [])),
    }
    
    total = sum(counts.values())
    
    # Build the breakdown string for the hero: "10+4+4+5+4+3+3"
    breakdown = '+'.join(str(v) for v in counts.values())
    
    return total, counts, breakdown


def validate_counts(total, counts):
    """Ensure the discovery count math adds up."""
    recalculated = sum(counts.values())
    if recalculated != total:
        print(f"ERROR: Discovery count mismatch. Total={total}, Recalculated={recalculated}")
        print(f"Breakdown: {counts}")
        return False
    return True


def build_investor_cards_html(investors_data):
    """
    Build investor card HTML from structured data.
    Uses the DTI-pattern: score ring, narrative, INTRO PATH + APPROACH boxes.
    
    CRITICAL: Every investor name comes from the database. Never fabricated.
    """
    if not investors_data or not investors_data.get('matches'):
        return '<p class="empty-state">No investor matches found.</p>'
    
    cards_html = []
    for inv in investors_data['matches']:
        # Build score ring SVG
        score = inv.get('score', 0)
        # SVG circle math: circumference = 2 * pi * r, offset = circ * (1 - score/100)
        
        # Build insight bullets
        insights_html = ''.join(
            f'<div class="inv-insight">{insight}</div>'
            for insight in inv.get('insights', [])
        )
        
        # Build the card (simplified, actual template has full HTML structure)
        card = f'''
        <div class="inv" data-score="{score}" data-db-id="{inv.get('db_id', '')}">
            <!-- Collapsed row -->
            <div class="inv-top" onclick="togInv(this)">
                <div class="inv-score-ring" data-score="{score}">
                    <span class="inv-score-num">{score}</span>
                </div>
                <div class="inv-info">
                    <div class="inv-name">{inv.get('name', 'Unknown')}</div>
                    <div class="inv-fund">{inv.get('fund', 'Unknown Fund')}</div>
                </div>
                <div class="inv-badge badge-{inv.get('action_level', 'watch')}">{inv.get('action_level', 'WATCH').upper()}</div>
            </div>
            <!-- Expanded detail -->
            <div class="inv-det">
                <div class="inv-det-in">
                    <div class="inv-narrative">{inv.get('thesis_summary', '')}</div>
                    <div class="inv-boxes">
                        <div class="inv-box">
                            <div class="inv-box-label">INTRO PATH</div>
                            <div class="inv-box-text">{inv.get('intro_path', {}).get('detail', 'Research needed')}</div>
                        </div>
                        <div class="inv-box">
                            <div class="inv-box-label">APPROACH</div>
                            <div class="inv-box-text">{inv.get('approach', '')}</div>
                        </div>
                    </div>
                    <div class="inv-insights">{insights_html}</div>
                </div>
            </div>
        </div>
        '''
        cards_html.append(card)
    
    return '\n'.join(cards_html)


def build_opportunity_cards_html(synthesis_data):
    """
    Build creative opportunity cards with full anatomy:
    narrative, dependencies, sequencing, current/activated state,
    people, funding pathway, metrics, timeline, confidence.
    """
    if not synthesis_data or not synthesis_data.get('creative_opportunities'):
        return '<p class="empty-state">No opportunities generated.</p>'
    
    cards_html = []
    border_colors = ['var(--sage)', 'var(--blue)', 'var(--peach)', 'var(--steel)']
    
    for i, opp in enumerate(synthesis_data['creative_opportunities']):
        color = border_colors[i % len(border_colors)]
        
        # Build dependencies HTML
        deps_html = ''.join(
            f'<div class="opp-dep"><strong>{dep.get("label", "")}:</strong> {dep.get("detail", "")}</div>'
            for dep in opp.get('dependencies', [])
        )
        
        # Build sequencing tags
        seq_html = ''.join(
            f'<span class="opp-seq-tag seq-{tag.get("type", "needs")}">{tag.get("label", "")}: {tag.get("detail", "")}</span>'
            for tag in opp.get('sequencing', [])
        )
        
        # Build metrics
        metrics_html = ''.join(
            f'''<div class="opp-metric">
                <div class="opp-metric-n">{m.get("value", "")}</div>
                <div class="opp-metric-l">{m.get("label", "")}</div>
            </div>'''
            for m in opp.get('metrics', [])
        )
        
        # Build timeline
        timeline_html = ''.join(
            f'<div class="opp-tl-item"><span class="opp-tl-wk">{step.get("period", "")}:</span> {step.get("action", "")}</div>'
            for step in opp.get('timeline', [])
        )
        
        # Build people tags
        people_html = ''.join(
            f'<span class="opp-tag">{person}</span>'
            for person in opp.get('people', [])
        )
        
        # Confidence bar
        conf = opp.get('confidence', 50)
        conf_class = 'conf-hi' if conf >= 65 else 'conf-md'
        
        # TODO: Full card HTML assembly using template patterns from v7
        # This is a simplified version showing the structure
        
        cards_html.append(f'<!-- Opportunity {i+1}: {opp.get("name", "")} -->')
    
    return '\n'.join(cards_html)


def build_grant_cards_html(grants_data):
    """Build grant section from verified grant data."""
    # TODO: Implement using grant-db.md patterns
    pass


def build_competitive_html(synthesis_data):
    """Build competitive position section with structured factor cards."""
    # TODO: Implement using v7 comp-factor pattern
    pass


def inject_data_into_template(template_html, data, phase=1):
    """
    Replace data slots in the HTML template with actual content.
    
    Data slots in the template use the pattern: {{SLOT_NAME}}
    """
    total, counts, breakdown = calculate_discovery_count(data)
    
    company = data.get('company', {}).get('company', {})
    
    replacements = {
        '{{COMPANY_NAME}}': company.get('name', 'Company'),
        '{{COMPANY_DESCRIPTION}}': company.get('description', ''),
        '{{COMPANY_SECTOR}}': company.get('sector', ''),
        '{{DISCOVERY_COUNT}}': str(total),
        '{{DISCOVERY_BREAKDOWN}}': breakdown,
        '{{PHASE}}': str(phase),
        '{{GENERATION_DATE}}': datetime.now().strftime('%B %d, %Y'),
        '{{INVESTOR_CARDS}}': build_investor_cards_html(data.get('investors')),
        '{{OPPORTUNITY_CARDS}}': build_opportunity_cards_html(data.get('synthesis')),
        # TODO: Add all remaining slot replacements
        '{{TOP_INVESTOR_SCORE}}': str(data.get('investors', {}).get('matches', [{}])[0].get('score', 0)) if data.get('investors', {}).get('matches') else '0',
        '{{GRANT_PIPELINE_TOTAL}}': data.get('grants', {}).get('pipeline_total', '$0'),
    }
    
    output_html = template_html
    for slot, value in replacements.items():
        output_html = output_html.replace(slot, str(value))
    
    return output_html


def generate_verification_log(data, output_path):
    """Create verification log for post-generation quality check."""
    log = {
        'generated_at': datetime.now().isoformat(),
        'discovery_count': calculate_discovery_count(data)[0],
        'discovery_breakdown': calculate_discovery_count(data)[1],
        'investors_from_db': all(
            inv.get('db_id') for inv in data.get('investors', {}).get('matches', [])
        ),
        'grants_web_verified': all(
            grant.get('amount_scraped_date') for grant in data.get('grants', {}).get('programs', [])
        ),
        'unverified_claims': [
            claim for step_data in data.values()
            if isinstance(step_data, dict)
            for claim in step_data.get('unverified_claims', [])
        ],
        'confidence_scores_cited': all(
            opp.get('confidence_reasoning')
            for opp in data.get('synthesis', {}).get('creative_opportunities', [])
        ),
    }
    
    with open(output_path, 'w') as f:
        json.dump(log, f, indent=2)
    
    return log


def main():
    parser = argparse.ArgumentParser(description='Assemble a Growth Playbook from pipeline data')
    parser.add_argument('--company-slug', required=True, help='Company slug for file paths')
    parser.add_argument('--phase', type=int, default=1, choices=[1, 2, 3], help='Playbook phase')
    args = parser.parse_args()
    
    # Load template
    with open(TEMPLATE_PATH, 'r') as f:
        template_html = f.read()
    
    # Load step data
    data = load_step_data(args.company_slug)
    
    # Calculate and validate counts
    total, counts, breakdown = calculate_discovery_count(data)
    if not validate_counts(total, counts):
        print("ERROR: Discovery count validation failed. Aborting.")
        sys.exit(1)
    
    # Inject data into template
    output_html = inject_data_into_template(template_html, data, phase=args.phase)
    
    # Write output
    output_dir = os.path.join(DATA_DIR, args.company_slug)
    output_path = os.path.join(output_dir, 'playbook.html')
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write(output_html)
    
    print(f"Playbook generated: {output_path}")
    print(f"Total discoveries: {total} ({breakdown})")
    
    # Generate verification log
    verify_path = os.path.join(output_dir, 'verification-log.json')
    log = generate_verification_log(data, verify_path)
    print(f"Verification log: {verify_path}")
    
    if log.get('unverified_claims'):
        print(f"WARNING: {len(log['unverified_claims'])} unverified claims found")


if __name__ == '__main__':
    main()
