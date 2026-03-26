#!/usr/bin/env python3
"""
Step 1: Deep Company Research (Self-Contained)
Model: Haiku with web search tool
Input: company name + website URL + slug
Output: data/[slug]/step1-company.json

Deep DD engine:
  1. Crawl the company website (all pages)
  2. Web search via Anthropic API (funding, news, patents, regulatory, etc.)
  3. Read uploaded PDFs (pitch decks) if present in data/{slug}/
  4. Read uploaded transcripts (.md files) if present
  5. Extract structured company intelligence via Haiku

Every factual claim must have a source_url.
"""

import json
import os
# Load API keys from .env files
for env_file in ["/home/openclaw/radar-platform/.env", "/home/openclaw/.openclaw/workspace-bd/.env"]:
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

import sys
import re
import time
import glob as globmod
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SKILL_ROOT = Path("/home/openclaw/playbook-skill")
MAX_PAGES = 10
SCRAPE_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; ClimateDoorResearchBot/1.0)"

VALID_PRIMARY_SECTORS = [
    "Ag & Food", "Buildings & Smart Cities", "Carbon", "Circular Economy",
    "Clean Industry / Advanced Manufacturing", "Climate Intelligence & Software",
    "Digital Services", "Energy & Storage", "Finance Policy & Markets",
    "Nature-based & Community Solutions", "Transportation",
    "Water & Decontamination", "Other"
]

VALID_STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Growth", "Bridge", "IPO", "PubCo"]

# ---------------------------------------------------------------------------
# Web fetching helpers
# ---------------------------------------------------------------------------
http_client = httpx.Client(
    timeout=SCRAPE_TIMEOUT,
    follow_redirects=True,
    headers={"User-Agent": USER_AGENT},
)


def fetch_page(url: str) -> str | None:
    try:
        resp = http_client.get(url)
        resp.raise_for_status()
        return resp.text[:200_000]
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None


def extract_text_from_html(html: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_links(html: str, base_url: str) -> list[str]:
    from urllib.parse import urljoin, urlparse
    base_domain = urlparse(base_url).netloc
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    internal = []
    skip_domains = {'p.yotpo.com', 'www.googletagmanager.com', 'cdn.shopify.com',
                    'fonts.googleapis.com', 'www.google.com', 'www.facebook.com',
                    'twitter.com', 'instagram.com', 'tiktok.com'}
    for link in links:
        if link.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        full = urljoin(base_url, link)
        parsed = urlparse(full)
        if parsed.netloc in skip_domains:
            continue
        if parsed.netloc == base_domain and parsed.scheme in ('http', 'https'):
            if any(full.lower().endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.zip', '.mp4', '.webp']):
                continue
            if '.oembed' in full:
                continue
            clean = parsed._replace(fragment='').geturl()
            if clean not in internal:
                internal.append(clean)
    return internal


def crawl_website(url: str, max_pages: int = MAX_PAGES) -> dict[str, str]:
    from urllib.parse import urlparse
    if not url.startswith('http'):
        url = 'https://' + url

    # Try HTTPS first, fall back to HTTP if it fails
    try:
        test = http_client.get(url)
        test.raise_for_status()
    except Exception:
        http_url = url.replace('https://', 'http://')
        print(f"  HTTPS failed, trying HTTP: {http_url}")
        try:
            test = http_client.get(http_url)
            test.raise_for_status()
            url = http_url
        except Exception:
            print(f"  [WARN] Both HTTPS and HTTP failed for {url}")
            pass

    visited = {}
    queue = [url]
    priority_paths = ['/about', '/team', '/partners', '/clients', '/products', '/solutions',
                      '/technology', '/investors', '/news', '/press', '/careers', '/contact',
                      '/case-studies', '/customers']

    print(f"  Crawling {url} (max {max_pages} pages)...")

    while queue and len(visited) < max_pages:
        current = queue.pop(0)
        if current in visited:
            continue

        html = fetch_page(current)
        if html is None:
            visited[current] = ""
            continue

        text = extract_text_from_html(html)
        visited[current] = text
        print(f"    [{len(visited)}/{max_pages}] {current[:80]}... ({len(text)} chars)")

        if len(visited) < max_pages:
            new_links = extract_links(html, current)
            for link in new_links:
                if link not in visited and link not in queue:
                    path = urlparse(link).path.lower()
                    if any(p in path for p in priority_paths):
                        queue.insert(0, link)
                    else:
                        queue.append(link)

    return visited


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {i+1}]\n{page_text}")
        result = "\n\n".join(text_parts)
        print(f"  Extracted {len(result)} chars from PDF: {os.path.basename(pdf_path)}")
        return result
    except Exception as e:
        print(f"  [WARN] Failed to extract PDF {pdf_path}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Web search via Anthropic API
# ---------------------------------------------------------------------------

def run_web_search(client: anthropic.Anthropic, company_name: str, website: str) -> str:
    """Use Haiku with web search tool to do comprehensive research."""
    print(f"\n  Running web search research for {company_name}...")

    search_prompt = f"""Search the web comprehensively for everything about "{company_name}" ({website}). I need:

1. Funding history - search for "{company_name} funding round", "{company_name} investment"
2. Team/founders - search for "{company_name} founder", "{company_name} CEO", key team members
3. Product details and traction
4. Patents - search "{company_name} patent"
5. Certifications/regulatory - search "{company_name} Health Canada", "{company_name} certification", "{company_name} FDA", "{company_name} ISO"
6. Recent news (last 12 months) - search "{company_name} news 2025 2026", "{company_name} announcement"
7. Press releases - search "{company_name} press release"
8. Competitors in the same space
9. LinkedIn company info - search "{company_name} LinkedIn"
10. Crunchbase profile - search "{company_name} Crunchbase"

For each piece of information found, note the source URL. Be thorough - search multiple queries.
Return ALL raw information you find, organized by category. Include source URLs for everything."""

    t0 = time.time()
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=8192,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": search_prompt}],
    )
    elapsed = time.time() - t0

    # Extract all text blocks from the response
    text_parts = []
    search_count = 0
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            text_parts.append(block.text)
        if block.type == 'server_tool_use':
            search_count += 1

    result = "\n".join(text_parts)
    print(f"  Web search complete in {elapsed:.1f}s ({search_count} searches, {response.usage.input_tokens}in/{response.usage.output_tokens}out)")
    return result


# ---------------------------------------------------------------------------
# Haiku extraction (structured JSON from all raw content)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a company research analyst for ClimateDoor, a climate venture advisory firm.
You are extracting structured company intelligence from raw research content.

CRITICAL RULES:
1. Every factual claim MUST have a source_url pointing to where you found it. If you cannot cite a source, mark "verified": false.
2. NEVER fabricate information. If data is not in the provided content, leave the field null or empty.
3. For sector classification, you MUST use one of these exact values for primary sector:
   {sectors}
4. For venture stage, use one of: {stages}
5. TRL assessment must cite specific evidence (product maturity, pilots, certifications).
6. Distinguish between government BUYER logos (they purchased the tech) and government FUNDER logos (they gave a grant).

Output ONLY valid JSON matching the schema below. No commentary, no markdown fences."""

EXTRACTION_USER_PROMPT = """Research the company "{company_name}" ({website}).

Here is all the content I gathered from various sources:

--- COMPANY WEBSITE CONTENT ---
{website_content}

--- WEB SEARCH RESULTS ---
{web_search_content}

--- UPLOADED PITCH DECK ---
{pdf_content}

--- UPLOADED TRANSCRIPT ---
{transcript_content}

--- USER NOTES / INSTRUCTIONS ---
{notes_content}

Based on this content, extract structured intelligence into this exact JSON schema:

{{
  "company": {{
    "name": "{company_name}",
    "website": "{website}",
    "description": "string - what the company does",
    "description_source": "url where description was found",
    "founded": "year or null",
    "stage": "one of the valid stages or null",
    "stage_source": "url or reasoning",
    "sector": "MUST be from the valid primary sector picklist",
    "sub_sector": "more specific classification",
    "trl": "1-9 integer or null",
    "trl_source": "url or reasoning for TRL assessment",
    "geography": {{
      "hq": "city, province/state, country",
      "operations": ["list of locations"]
    }}
  }},
  "product": {{
    "description": "string - detailed product/service description",
    "key_claims": [
      {{"claim": "string", "source_url": "url", "verified": true}}
    ],
    "regulatory_status": {{
      "iso_certifications": {{"status": "string or unknown", "source_url": "url or null"}},
      "fda_510k": {{"status": "cleared | pending | not_applicable | unknown", "source_url": "url or null"}},
      "ce_marking": {{"status": "certified | pending | unknown", "source_url": "url or null"}},
      "health_canada": {{"status": "string or unknown", "source_url": "url or null"}}
    }},
    "ip": {{
      "patents": [
        {{"title": "string", "number": "string or null", "jurisdiction": "string", "source_url": "url"}}
      ]
    }}
  }},
  "funding": {{
    "total_raised": "dollar amount or null",
    "total_raised_source": "url or null",
    "current_raise": {{
      "amount": "dollar amount or null",
      "stage": "string or null",
      "use_of_funds": "string or null",
      "source_url": "url or null"
    }},
    "rounds": [
      {{"date": "string", "amount": "string", "type": "string", "investors": ["list"], "source_url": "url"}}
    ]
  }},
  "team": {{
    "founders": [
      {{"name": "string", "title": "string", "linkedin": "url or null", "background_summary": "string"}}
    ],
    "employee_count": "number or null",
    "employee_count_source": "url or null"
  }},
  "market": {{
    "target_buyers": ["list of buyer types from their site"],
    "competitors_mentioned": ["any competitors referenced"],
    "market_size_claims": [
      {{"claim": "string", "source_url": "url", "verified": true}}
    ]
  }},
  "traction": {{
    "website_logos": [
      {{
        "name": "Organization name",
        "type": "government_buyer | government_funder | enterprise | accelerator | university | other",
        "significance": "Why this matters",
        "source_url": "url of page where found"
      }}
    ],
    "government_buyer_traction": false,
    "military_defense_traction": false,
    "customer_count": {{"claimed": "string or null", "source_url": "url or null", "verified": false}},
    "case_studies": [
      {{"customer": "string", "outcome": "string", "source_url": "url"}}
    ],
    "trial_conversion_data": null
  }},
  "signals": {{
    "recent_news": [
      {{"headline": "string", "date": "string", "source_url": "url", "relevance": "string"}}
    ],
    "partnerships": [
      {{"partner": "string", "type": "string", "source_url": "url"}}
    ],
    "sector_temperature": {{
      "assessment": "hot | warming | stable | cooling | cold",
      "evidence": ["Specific evidence points"],
      "competitor_funding": []
    }}
  }},
  "data_gaps": [
    "List of things looked for but not found - these become Key Questions in Step 6"
  ],
  "generation_metadata": {{
    "generated_at": "{timestamp}",
    "sources_checked": 0,
    "sources_reached": 0,
    "claims_verified": 0,
    "claims_unverified": 0
  }}
}}

Be thorough but honest. Mark anything uncertain as unverified. List all data gaps."""


def run_haiku_extraction(client: anthropic.Anthropic, company_name: str, website: str,
                         website_content: str, web_search_content: str,
                         pdf_content: str, transcript_content: str,
                         notes_content: str = "") -> dict:
    """Send all gathered content to Haiku for structured extraction."""
    system = EXTRACTION_SYSTEM_PROMPT.format(
        sectors=", ".join(VALID_PRIMARY_SECTORS),
        stages=", ".join(VALID_STAGES),
    )

    user_msg = EXTRACTION_USER_PROMPT.format(
        company_name=company_name,
        website=website,
        website_content=website_content[:60000] or "[No website content scraped]",
        web_search_content=web_search_content[:40000] or "[No web search results]",
        pdf_content=pdf_content[:30000] or "[No pitch deck uploaded]",
        transcript_content=transcript_content[:20000] or "[No transcript uploaded]",
        notes_content=notes_content[:10000] or "[No user notes provided]",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    print(f"\n  Calling Haiku for structured extraction...")
    print(f"  Input size: ~{(len(system) + len(user_msg)) // 1000}K chars")

    t0 = time.time()
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    elapsed = time.time() - t0

    raw = response.content[0].text
    print(f"  Haiku responded in {elapsed:.1f}s ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] Direct JSON parse failed ({e}), trying to extract JSON object...")
        depth = 0
        start = raw.index('{')
        for i in range(start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(raw[start:i+1])
                        print(f"  [FIX] Extracted valid JSON ({i+1} chars of {len(raw)})")
                        break
                    except json.JSONDecodeError:
                        continue
        else:
            print(f"  [ERROR] Could not extract valid JSON from Haiku output")
            return {"error": str(e), "raw_output": raw[:2000]}

    return data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_sector(data: dict) -> dict:
    sector = data.get("company", {}).get("sector", "")
    if sector and sector not in VALID_PRIMARY_SECTORS:
        for valid in VALID_PRIMARY_SECTORS:
            if sector.lower() in valid.lower() or valid.lower() in sector.lower():
                print(f"  [FIX] Sector '{sector}' -> '{valid}'")
                data["company"]["sector"] = valid
                return data
        print(f"  [WARN] Invalid sector '{sector}', setting to 'Other'")
        data["company"]["sector"] = "Other"
    return data


def validate_stage(data: dict) -> dict:
    stage = data.get("company", {}).get("stage")
    if stage and stage not in VALID_STAGES:
        for valid in VALID_STAGES:
            if stage.lower() == valid.lower():
                data["company"]["stage"] = valid
                return data
        print(f"  [WARN] Invalid stage '{stage}', setting to null")
        data["company"]["stage"] = None
    return data


def count_verified(data: dict) -> tuple[int, int]:
    verified = 0
    unverified = 0
    for claim in data.get("product", {}).get("key_claims", []):
        if claim.get("verified"):
            verified += 1
        else:
            unverified += 1
    for claim in data.get("market", {}).get("market_size_claims", []):
        if claim.get("verified"):
            verified += 1
        else:
            unverified += 1
    traction = data.get("traction", {})
    if traction.get("customer_count", {}) and traction["customer_count"].get("verified"):
        verified += 1
    elif traction.get("customer_count", {}) and traction["customer_count"].get("claimed"):
        unverified += 1
    return verified, unverified


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_step1(company_name: str, website: str, slug: str | None = None) -> Path:
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', company_name.lower()).strip('-')

    output_dir = SKILL_ROOT / "data" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "step1-company.json"

    print(f"=" * 60)
    print(f"STEP 1: Deep Company Research")
    print(f"Company: {company_name}")
    print(f"Website: {website}")
    print(f"Output:  {output_path}")
    print(f"=" * 60)

    client = anthropic.Anthropic()

    # --- Phase 1: Crawl website ---
    print(f"\n[1/5] Crawling company website...")
    website_pages = crawl_website(website, max_pages=MAX_PAGES)
    website_content = "\n\n".join(
        f"[PAGE: {url}]\n{text}" for url, text in website_pages.items() if text
    )
    sources_reached = sum(1 for t in website_pages.values() if t)

    # --- Phase 2: Web search via Anthropic API ---
    print(f"\n[2/5] Running web search research...")
    web_search_content = run_web_search(client, company_name, website)
    if web_search_content:
        sources_reached += 1

    # --- Phase 3: Read uploaded PDFs ---
    print(f"\n[3/5] Checking for uploaded PDFs...")
    pdf_content = ""
    pdf_files = list(output_dir.glob("*.pdf"))
    if pdf_files:
        for pdf_file in pdf_files:
            print(f"  Found PDF: {pdf_file.name}")
            extracted = extract_pdf_text(str(pdf_file))
            if extracted:
                pdf_content += f"\n[PDF: {pdf_file.name}]\n{extracted}\n"
                sources_reached += 1
    else:
        print(f"  No PDF files found in {output_dir}")

    # --- Phase 4: Read uploaded transcripts ---
    print(f"\n[4/5] Checking for uploaded transcripts...")
    transcript_content = ""
    md_files = list(output_dir.glob("*.md"))
    if md_files:
        for md_file in md_files:
            print(f"  Found transcript: {md_file.name}")
            try:
                text = md_file.read_text()
                transcript_content += f"\n[TRANSCRIPT: {md_file.name}]\n{text}\n"
                sources_reached += 1
                print(f"  Read {len(text)} chars from {md_file.name}")
            except Exception as e:
                print(f"  [WARN] Failed to read {md_file.name}: {e}")
    else:
        print(f"  No .md transcript files found in {output_dir}")

    # --- Phase 4b: Read uploaded DOCX files ---
    docx_files = list(output_dir.glob("*.docx"))
    for docx_file in docx_files:
        print(f"  Found DOCX: {docx_file.name}")
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(str(docx_file))
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            if text:
                transcript_content += f"\n[DOCX: {docx_file.name}]\n{text}\n"
                sources_reached += 1
                print(f"  Read {len(text)} chars from {docx_file.name}")
        except Exception as e:
            print(f"  [WARN] Failed to read {docx_file.name}: {e}")

    # --- Phase 4c: Read user notes ---
    notes_content = ""
    notes_file = output_dir / "notes.txt"
    if notes_file.exists():
        try:
            notes_content = notes_file.read_text().strip()
            print(f"  Found notes.txt: {len(notes_content)} chars")
        except Exception as e:
            print(f"  [WARN] Failed to read notes.txt: {e}")

    total_sources = 2 + len(pdf_files) + len(md_files) + len(docx_files)
    print(f"\n  Sources checked: {total_sources}, reached: {sources_reached}")
    total_content = len(website_content) + len(web_search_content) + len(pdf_content) + len(transcript_content) + len(notes_content)
    print(f"  Total content: ~{total_content // 1000}K chars")

    # --- Phase 5: Haiku extraction ---
    print(f"\n[5/5] Running Haiku structured extraction...")
    data = run_haiku_extraction(
        client=client,
        company_name=company_name,
        website=website,
        website_content=website_content,
        web_search_content=web_search_content,
        pdf_content=pdf_content,
        transcript_content=transcript_content,
        notes_content=notes_content,
    )

    if "error" in data:
        print(f"\n  [FAIL] Extraction failed. Saving raw output for debugging.")
        error_path = output_dir / "step1-company-ERROR.json"
        with open(error_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"  Saved to: {error_path}")
        sys.exit(1)

    # --- Validate ---
    print(f"\n  Validating extraction...")
    data = validate_sector(data)
    data = validate_stage(data)

    verified, unverified = count_verified(data)
    if "generation_metadata" not in data:
        data["generation_metadata"] = {}
    data["generation_metadata"].update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_checked": total_sources,
        "sources_reached": sources_reached,
        "claims_verified": verified,
        "claims_unverified": unverified,
        "model": HAIKU_MODEL,
        "website_pages_crawled": len(website_pages),
        "web_search_used": True,
        "pdfs_read": len(pdf_files),
        "transcripts_read": len(md_files),
    })

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"STEP 1 COMPLETE")
    print(f"  Output: {output_path}")
    print(f"  Sector: {data.get('company', {}).get('sector', 'N/A')}")
    print(f"  Stage:  {data.get('company', {}).get('stage', 'N/A')}")
    print(f"  TRL:    {data.get('company', {}).get('trl', 'N/A')}")
    print(f"  Claims: {verified} verified, {unverified} unverified")
    print(f"  Data gaps: {len(data.get('data_gaps', []))}")
    print(f"  Logos found: {len(data.get('traction', {}).get('website_logos', []))}")
    print(f"{'=' * 60}")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 step1_company_research.py <company_name> <website> [slug]")
        print("Example: python3 step1_company_research.py 'Fuse Power' 'fusepower.com' 'fuse-power'")
        sys.exit(1)

    company_name = sys.argv[1]
    website = sys.argv[2]
    slug = sys.argv[3] if len(sys.argv) > 3 else None

    output = run_step1(company_name, website, slug)
    print(f"\nDone. Output at: {output}")
