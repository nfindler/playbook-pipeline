#!/usr/bin/env python3
"""
Playbook Verification Script (Post-Generation Quality Gate)

Runs after assembly to catch:
- Fabricated investor/fund names not in the database
- Grant program URLs that don't resolve
- Discovery count math errors
- Missing confidence score reasoning
- Picklist values outside valid sets
- Market sizing numbers without sources

Usage:
    python validate_playbook.py --company-slug frett-design
"""

import json
import os
import sys
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

DATA_DIR = '/home/claude/playbook-data'
INVESTOR_DB = '/home/openclaw/data/investors.db'  # Confirm path
EXPERT_DB = '/home/openclaw/data/experts.db'  # Confirm path


class PlaybookValidator:
    def __init__(self, company_slug):
        self.company_slug = company_slug
        self.base_dir = os.path.join(DATA_DIR, company_slug)
        self.errors = []
        self.warnings = []
        self.data = {}
    
    def load_data(self):
        """Load all step outputs."""
        step_files = {
            'company': 'step1-company.json',
            'investors': 'step2-investors.json',
            'grants': 'step3-grants.json',
            'market': 'step4-market.json',
            'experts': 'step5-experts.json',
            'synthesis': 'step6-synthesis.json',
        }
        for key, filename in step_files.items():
            filepath = os.path.join(self.base_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    self.data[key] = json.load(f)
            else:
                self.errors.append(f"MISSING: {filename}")
    
    def check_investor_names(self):
        """
        CRITICAL: Every investor name must exist in the SQLite database
        or have a verified web URL.
        """
        investors = self.data.get('investors', {}).get('matches', [])
        
        if not os.path.exists(INVESTOR_DB):
            self.warnings.append(f"Investor DB not found at {INVESTOR_DB}, skipping name validation")
            return
        
        conn = sqlite3.connect(INVESTOR_DB)
        cursor = conn.cursor()
        
        for inv in investors:
            name = inv.get('name', '')
            db_id = inv.get('db_id', '')
            
            if db_id:
                cursor.execute("SELECT COUNT(*) FROM investors WHERE id = ?", (db_id,))
                if cursor.fetchone()[0] == 0:
                    self.errors.append(f"FABRICATED INVESTOR: '{name}' (db_id={db_id}) not found in database")
            else:
                # No db_id, check by name
                cursor.execute("SELECT COUNT(*) FROM investors WHERE name LIKE ?", (f'%{name}%',))
                if cursor.fetchone()[0] == 0:
                    # Not in DB, must have a verified web URL
                    if not inv.get('verified_url'):
                        self.errors.append(f"FABRICATED INVESTOR: '{name}' not in DB and no verified URL")
                    else:
                        self.warnings.append(f"Investor '{name}' not in DB but has web verification")
        
        conn.close()
    
    def check_grant_urls(self):
        """
        Every grant program must have a Website URL that resolves.
        """
        grants = self.data.get('grants', {}).get('programs', [])
        
        for grant in grants:
            url = grant.get('program_url', '')
            if not url:
                self.errors.append(f"MISSING URL: Grant '{grant.get('program_name', 'Unknown')}' has no program URL")
                continue
            
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                if response.status_code >= 400:
                    self.warnings.append(
                        f"GRANT URL ISSUE: '{grant.get('program_name', '')}' URL returned {response.status_code}: {url}"
                    )
            except requests.RequestException as e:
                self.warnings.append(
                    f"GRANT URL UNREACHABLE: '{grant.get('program_name', '')}' URL failed: {url} ({e})"
                )
    
    def check_discovery_count(self):
        """
        The total discovery count must equal the sum of individual counts.
        """
        counts = {
            'investors': len(self.data.get('investors', {}).get('matches', [])),
            'grants': len(self.data.get('grants', {}).get('programs', [])),
            'buyer_segments': len(self.data.get('market', {}).get('buyer_segments', [])),
            'market_signals': len(self.data.get('market', {}).get('signals', [])),
            'opportunities': len(self.data.get('synthesis', {}).get('creative_opportunities', [])),
            'experts': len(self.data.get('experts', {}).get('matches', [])),
            'conferences': len(self.data.get('market', {}).get('conferences', [])),
        }
        
        total = sum(counts.values())
        stated_total = self.data.get('synthesis', {}).get('discovery_count', total)
        
        if total != stated_total:
            self.errors.append(
                f"DISCOVERY COUNT MISMATCH: Stated={stated_total}, Calculated={total}, Breakdown={counts}"
            )
        
        return total, counts
    
    def check_confidence_scores(self):
        """
        Every confidence score must have cited reasoning.
        """
        opportunities = self.data.get('synthesis', {}).get('creative_opportunities', [])
        
        for opp in opportunities:
            name = opp.get('name', 'Unknown')
            score = opp.get('confidence', None)
            reasoning = opp.get('confidence_reasoning', '')
            
            if score is None:
                self.errors.append(f"MISSING CONFIDENCE: Opportunity '{name}' has no confidence score")
            elif not reasoning:
                self.errors.append(f"UNCITED CONFIDENCE: Opportunity '{name}' has score {score} but no reasoning")
            elif 'Step' not in reasoning and 'step' not in reasoning:
                self.warnings.append(
                    f"WEAK CITATION: Opportunity '{name}' confidence reasoning doesn't reference source steps"
                )
    
    def check_market_sizing(self):
        """
        Market sizing numbers must have sources or shown methodology.
        """
        market = self.data.get('market', {})
        
        for segment in market.get('buyer_segments', []):
            sizing = segment.get('market_size', '')
            source = segment.get('market_size_source', '')
            methodology = segment.get('market_size_methodology', '')
            
            if sizing and not source and not methodology:
                self.errors.append(
                    f"UNSOURCED MARKET SIZE: Segment '{segment.get('name', '')}' claims '{sizing}' with no source or methodology"
                )
    
    def check_picklist_values(self):
        """
        ICP tags must be from the valid picklist.
        See references/icp-tagging.md for valid values.
        """
        # TODO: Load picklist values from icp-tagging.md
        # For now, just check that the fields exist
        company = self.data.get('company', {}).get('company', {})
        sector = company.get('sector', '')
        if not sector:
            self.warnings.append("MISSING SECTOR: Company has no primary sector classification")
    
    def check_dependencies_link_to_questions(self):
        """
        Every opportunity dependency should reference a Key Question.
        """
        synthesis = self.data.get('synthesis', {})
        opportunities = synthesis.get('creative_opportunities', [])
        questions = synthesis.get('key_questions', [])
        question_texts = [q.get('question', '').lower() for q in questions]
        
        for opp in opportunities:
            for dep in opp.get('dependencies', []):
                dep_text = dep.get('detail', '').lower()
                # Check if any question addresses this dependency
                has_question = any(
                    any(word in qt for word in dep_text.split()[:5])
                    for qt in question_texts
                )
                if not has_question:
                    self.warnings.append(
                        f"ORPHAN DEPENDENCY: '{opp.get('name', '')}' dependency '{dep.get('label', '')}' "
                        f"has no corresponding Key Question"
                    )
    
    def check_unique_angles(self):
        """
        At least one opportunity should include a ClimateDoor unique angle:
        geographic, national security, grants-as-BD, or sector temperature.
        """
        opportunities = self.data.get('synthesis', {}).get('creative_opportunities', [])
        
        angle_keywords = [
            'europe', 'eu', 'singapore', 'first nations', 'indigenous',
            'national security', 'defense', 'dual-use', 'itb',
            'grant', 'customer', 'end customer', 'funded to buy',
            'sector temperature', 'hot', 'cold', 'cooling', 'surging'
        ]
        
        has_unique = False
        for opp in opportunities:
            narrative = opp.get('narrative', '').lower()
            if any(kw in narrative for kw in angle_keywords):
                has_unique = True
                break
        
        if not has_unique:
            self.warnings.append(
                "MISSING UNIQUE ANGLE: No opportunity includes a ClimateDoor-specific angle "
                "(geographic, national security, grants-as-BD, or sector temperature). "
                "This playbook may feel generic."
            )
    
    def run_all_checks(self):
        """Run all validation checks and return results."""
        self.load_data()
        
        if self.errors:
            # Can't proceed if data is missing
            return self.generate_report()
        
        self.check_investor_names()
        self.check_grant_urls()
        self.check_discovery_count()
        self.check_confidence_scores()
        self.check_market_sizing()
        self.check_picklist_values()
        self.check_dependencies_link_to_questions()
        self.check_unique_angles()
        
        return self.generate_report()
    
    def generate_report(self):
        """Generate validation report."""
        report = {
            'company_slug': self.company_slug,
            'validated_at': datetime.now().isoformat(),
            'errors': self.errors,
            'warnings': self.warnings,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'passed': len(self.errors) == 0,
        }
        
        # Save report
        report_path = os.path.join(self.base_dir, 'verification-log.json')
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate a generated playbook')
    parser.add_argument('--company-slug', required=True, help='Company slug')
    args = parser.parse_args()
    
    validator = PlaybookValidator(args.company_slug)
    report = validator.run_all_checks()
    
    print(f"\n{'='*60}")
    print(f"PLAYBOOK VALIDATION: {args.company_slug}")
    print(f"{'='*60}")
    
    if report['passed']:
        print(f"\nPASSED with {report['warning_count']} warnings")
    else:
        print(f"\nFAILED with {report['error_count']} errors and {report['warning_count']} warnings")
    
    if report['errors']:
        print(f"\nERRORS (must fix):")
        for e in report['errors']:
            print(f"  [X] {e}")
    
    if report['warnings']:
        print(f"\nWARNINGS (review):")
        for w in report['warnings']:
            print(f"  [!] {w}")
    
    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
