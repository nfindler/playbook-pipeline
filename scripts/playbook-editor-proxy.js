#!/usr/bin/env node
/**
 * ClimateDoor Playbook Editor API
 * Port 4300
 *
 * Endpoints:
 *   POST /api/playbooks/:slug/edit      - Direct JSON edit (no AI)
 *   POST /api/playbooks/:slug/prompt    - AI-powered edit via Sonnet
 *   POST /api/playbooks/:slug/upload    - Document upload + AI processing
 *   POST /api/playbooks/:slug/add-signal - Add market signal card
 *   POST /api/playbooks/:slug/remove    - Remove a card from any section
 *   GET  /api/playbooks/:slug/versions  - Version history
 *   POST /api/playbooks/:slug/rollback  - Rollback to a version
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');
const { URL } = require('url');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const PORT = 4300;
const SKILL_ROOT = '/home/openclaw/playbook-skill';
const DATA_DIR = path.join(SKILL_ROOT, 'data');
const DEPLOY_ROOT = '/var/www/climatedoor/playbooks';
const RADAR_DATA_DIR = '/home/openclaw/radar-platform/data/pages';
const STEP7_SCRIPT = path.join(SKILL_ROOT, 'scripts', 'step7_assemble.py');

// Load API key
let ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
if (!ANTHROPIC_API_KEY) {
  try {
    const envFile = fs.readFileSync('/home/openclaw/radar-platform/.env', 'utf8');
    const match = envFile.match(/^ANTHROPIC_API_KEY=(.+)$/m);
    if (match) ANTHROPIC_API_KEY = match[1].trim();
  } catch (e) {
    log('WARNING: Could not read API key from .env file');
  }
}

// Lazy-load Anthropic SDK
let Anthropic;
try {
  Anthropic = require('@anthropic-ai/sdk');
} catch (e) {
  log('WARNING: @anthropic-ai/sdk not found. Prompt/upload endpoints will fail.');
}

// Lazy-load multer and pdf-parse
let multer, pdfParse;
try { multer = require('multer'); } catch (e) { log('WARNING: multer not found'); }
try { pdfParse = require('pdf-parse'); } catch (e) { log('WARNING: pdf-parse not found'); }

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

/** lodash-style setByPath: setByPath(obj, 'a.b.0.c', val) */
function setByPath(obj, dotPath, value) {
  const keys = parsePath(dotPath);
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (cur[k] === undefined) {
      cur[k] = typeof keys[i + 1] === 'number' ? [] : {};
    }
    cur = cur[k];
  }
  cur[keys[keys.length - 1]] = value;
}

/** getByPath */
function getByPath(obj, dotPath) {
  const keys = parsePath(dotPath);
  let cur = obj;
  for (const k of keys) {
    if (cur === undefined || cur === null) return undefined;
    cur = cur[k];
  }
  return cur;
}

/** Parse dot-path into array of string/number keys */
function parsePath(dotPath) {
  const keys = [];
  // Split on dots and brackets: "a.b[0].c" -> ["a","b","0","c"]
  const parts = dotPath.replace(/\[(\d+)\]/g, '.$1').split('.');
  for (const p of parts) {
    if (p === '') continue;
    keys.push(/^\d+$/.test(p) ? parseInt(p, 10) : p);
  }
  return keys;
}

/** Read JSON file */
function readJSON(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

/** Write JSON file */
function writeJSON(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
}

/** Resolve step filename from step key */
function stepFile(slug, step) {
  const map = {
    step1: 'step1-company.json',
    step2: 'step2-investors.json',
    step2b: 'step2b-contacts.json',
    step3: 'step3-grants.json',
    step4: 'step4-market.json',
    step5: 'step5-experts.json',
    step6: 'step6-synthesis.json',
  };
  const fname = map[step];
  if (!fname) throw new Error(`Unknown step: ${step}`);
  return path.join(DATA_DIR, slug, fname);
}

/** Rebuild playbook (step7) and deploy */
function rebuild(slug) {
  log(`Rebuilding playbook for ${slug}...`);
  execSync(`python3 ${STEP7_SCRIPT} ${slug}`, {
    cwd: SKILL_ROOT,
    stdio: 'pipe',
    timeout: 900000,
  });
  // Copy output to deploy path
  const src = path.join(DATA_DIR, slug, 'playbook.html');
  const altSrc = path.join(SKILL_ROOT, 'output', slug, 'index.html');
  const deployDir = path.join(DEPLOY_ROOT, slug);
  const dest = path.join(deployDir, 'index.html');

  if (!fs.existsSync(deployDir)) {
    fs.mkdirSync(deployDir, { recursive: true });
  }

  // Try multiple possible output locations
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest);
  } else if (fs.existsSync(altSrc)) {
    fs.copyFileSync(altSrc, dest);
  } else {
    // The script may output directly to deploy path; verify it exists
    const templateOut = path.join(DEPLOY_ROOT, slug, 'index.html');
    if (!fs.existsSync(templateOut)) {
      log('WARNING: Could not find assembled HTML output. Checking common paths...');
      // Last resort: glob for any .html in the data dir
      const dataDir = path.join(DATA_DIR, slug);
      const htmlFiles = fs.readdirSync(dataDir).filter(f => f.endsWith('.html'));
      if (htmlFiles.length > 0) {
        fs.copyFileSync(path.join(dataDir, htmlFiles[0]), dest);
      }
    }
  }
  log(`Rebuild complete for ${slug}`);
}

// ---------------------------------------------------------------------------
// Version Control
// ---------------------------------------------------------------------------
function ensureVersionDir(slug) {
  const vDir = path.join(DATA_DIR, slug, 'versions');
  if (!fs.existsSync(vDir)) fs.mkdirSync(vDir, { recursive: true });
  return vDir;
}

function readVersionLog(slug) {
  const vDir = ensureVersionDir(slug);
  const logFile = path.join(vDir, 'version-log.json');
  if (fs.existsSync(logFile)) {
    return readJSON(logFile);
  }
  return { versions: [], current: 'v1.0.0' };
}

function writeVersionLog(slug, logData) {
  const vDir = ensureVersionDir(slug);
  writeJSON(path.join(vDir, 'version-log.json'), logData);
}

/**
 * Create a version backup.
 * changeType: 'patch' (direct edit), 'minor' (prompt edit), 'major' (full re-run)
 */
function createVersion(slug, changeType, changedFiles, extra = {}) {
  const vLog = readVersionLog(slug);
  const current = vLog.current || 'v1.0.0';
  const [major, minor, patch] = current.replace('v', '').split('.').map(Number);

  let next;
  if (changeType === 'major') next = `v${major + 1}.0.0`;
  else if (changeType === 'minor') next = `v${major}.${minor + 1}.0`;
  else next = `v${major}.${minor}.${patch + 1}`;

  const vDir = ensureVersionDir(slug);
  const snapDir = path.join(vDir, next);
  if (!fs.existsSync(snapDir)) fs.mkdirSync(snapDir, { recursive: true });

  // Copy affected files to snapshot
  for (const f of changedFiles) {
    const src = path.join(DATA_DIR, slug, f);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(snapDir, f));
    }
  }

  // Write metadata
  const metadata = {
    version: next,
    timestamp: new Date().toISOString(),
    change_type: changeType,
    prompt_text: extra.prompt || null,
    cost: extra.cost || null,
    changed_files: changedFiles,
  };
  writeJSON(path.join(snapDir, 'metadata.json'), metadata);

  // Update log
  vLog.versions.push(metadata);
  vLog.current = next;
  writeVersionLog(slug, vLog);

  log(`Version ${next} created for ${slug}`);
  return next;
}

// ---------------------------------------------------------------------------
// Section mapping for prompt endpoint
// ---------------------------------------------------------------------------
function resolveSection(section) {
  if (!section) return null;
  if (section === 'full') return { step: 'all', file: null, path: null };

  // Pillar sections
  const pillars = ['capital_pillar', 'grants_pillar', 'sales_pillar', 'signals_pillar'];
  if (pillars.includes(section)) {
    const key = section.replace('_pillar', '');
    return { step: 'step6', file: 'step6-synthesis.json', path: `strategy_pillars.${key}` };
  }

  // Opportunity
  let m = section.match(/^opportunity_(\d+)$/);
  if (m) return { step: 'step6', file: 'step6-synthesis.json', path: `creative_opportunities[${m[1]}]` };

  // Investor by db_id
  m = section.match(/^investor_(.+)$/);
  if (m) return { step: 'step2', file: 'step2-investors.json', path: 'investors', findBy: 'db_id', findVal: m[1] };

  // Buyer
  m = section.match(/^buyer_(\d+)$/);
  if (m) return { step: 'step4', file: 'step4-market.json', path: `buyer_segments[${m[1]}]` };

  // Signal
  m = section.match(/^signal_(\d+)$/);
  if (m) return { step: 'step4', file: 'step4-market.json', path: `market_signals[${m[1]}]` };

  // Grant
  m = section.match(/^grant_(\d+)$/);
  if (m) return { step: 'step3', file: 'step3-grants.json', path: `direct_grants[${m[1]}]` };

  // Indigenous
  m = section.match(/^indigenous_(\d+)$/);
  if (m) return { step: 'step4', file: 'step4-market.json', path: `indigenous_opportunities[${m[1]}]` };

  // Question
  m = section.match(/^question_(\d+)$/);
  if (m) return { step: 'step6', file: 'step6-synthesis.json', path: `key_questions[${m[1]}]` };

  // Competitive position
  if (section === 'competitive_position') {
    return { step: 'step6', file: 'step6-synthesis.json', path: 'competitive_position' };
  }

  // Alert
  m = section.match(/^alert_(\d+)$/);
  if (m) return { step: 'step6', file: 'step6-synthesis.json', path: `alerts[${m[1]}]` };

  // Expert
  m = section.match(/^expert_(\d+)$/);
  if (m) return { step: 'step5', file: 'step5-experts.json', path: `expert_matches[${m[1]}]` };

  // Hero
  if (section === 'hero') {
    return { step: 'step1', file: 'step1-company.json', path: 'company.description' };
  }

  // Full
  if (section === 'full') {
    return { step: 'all', file: null, path: null };
  }

  return null;
}

// ---------------------------------------------------------------------------
// Anthropic API helper
// ---------------------------------------------------------------------------
async function callSonnet(systemPrompt, userContent) {
  if (!Anthropic) throw new Error('Anthropic SDK not available');
  const client = new Anthropic({ apiKey: ANTHROPIC_API_KEY });

  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 8192,
    system: systemPrompt,
    messages: [{ role: 'user', content: userContent }],
  });

  const text = response.content.map(b => b.text || '').join('');
  const inputTokens = response.usage?.input_tokens || 0;
  const outputTokens = response.usage?.output_tokens || 0;
  // Sonnet pricing: $3/M input, $15/M output
  const cost = (inputTokens * 3 + outputTokens * 15) / 1_000_000;

  return { text, cost, inputTokens, outputTokens };
}

/** Extract JSON from a response that may contain markdown fences */
function extractJSON(text) {
  // Try direct parse first
  try { return JSON.parse(text); } catch (e) { /* continue */ }
  // Try extracting from code fences
  const m = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (m) {
    return JSON.parse(m[1].trim());
  }
  throw new Error('Could not parse JSON from AI response');
}

// ---------------------------------------------------------------------------
// Request parsing helpers
// ---------------------------------------------------------------------------
function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try { resolve(JSON.parse(body)); }
      catch (e) { reject(new Error('Invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

function sendJSON(res, status, data) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  });
  res.end(JSON.stringify(data));
}

// ---------------------------------------------------------------------------
// CLI-1212 v27: share-token store (file-backed JSON, append-only)
// ---------------------------------------------------------------------------
const crypto = require('crypto');
const SHARE_TOKENS_PATH = path.join(DATA_DIR, '_share_tokens.json');
const SHARE_TTL_DAYS = parseInt(process.env.PLAYBOOK_SHARE_TTL_DAYS || '7', 10);

function readShareTokens() {
  try {
    const raw = fs.readFileSync(SHARE_TOKENS_PATH, 'utf8');
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (_) { return []; }
}
function writeShareTokens(arr) {
  try { fs.writeFileSync(SHARE_TOKENS_PATH, JSON.stringify(arr, null, 2)); }
  catch (e) { log('share-tokens write error: ' + e.message); }
}
function generateShareToken() {
  return crypto.randomBytes(24).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function findShareToken(token) {
  const arr = readShareTokens();
  return arr.find(t => t.token === token) || null;
}
function incrementShareView(token) {
  const arr = readShareTokens();
  const t = arr.find(x => x.token === token);
  if (!t) return;
  t.view_count = (t.view_count || 0) + 1;
  t.last_viewed_at = new Date().toISOString();
  writeShareTokens(arr);
}
function pruneExpiredShareTokens() {
  const now = Date.now();
  const arr = readShareTokens();
  const kept = arr.filter(t => Date.parse(t.expires_at) > now);
  if (kept.length !== arr.length) writeShareTokens(kept);
}

// ---------------------------------------------------------------------------
// CLI-1212-3a v28: DOCX export.
// ---------------------------------------------------------------------------
const docxLib = require('docx');

function readPlaybookSection(slug, file) {
  try {
    const fp = path.join(DATA_DIR, slug, file);
    if (!fs.existsSync(fp)) return null;
    return JSON.parse(fs.readFileSync(fp, 'utf8'));
  } catch (_) { return null; }
}

const _DOCX_CTRL_RE = new RegExp('[\\x00-\\x1f\\x7f]', 'g');
function docxSafe(s, max) {
  if (s == null) return '';
  s = String(s).replace(_DOCX_CTRL_RE, '');
  if (max && s.length > max) s = s.slice(0, max - 1) + '...';
  return s;
}

function buildPlaybookDocx(slug) {
  const step1 = readPlaybookSection(slug, 'step1-company.json') || {};
  const hooksData = readPlaybookSection(slug, 'hooks.json');
  const step2 = readPlaybookSection(slug, 'step2-investors.json');
  const step2b = readPlaybookSection(slug, 'step2b-contacts.json');
  const step3 = readPlaybookSection(slug, 'step3-grants.json');
  const step4 = readPlaybookSection(slug, 'step4-market.json');
  const step5 = readPlaybookSection(slug, 'step5-experts.json');
  const step6 = readPlaybookSection(slug, 'step6-synthesis.json');

  const company = (step1.company && step1.company.name) || slug;
  const description = step1.company && step1.company.description || '';
  const sector = step1.company && step1.company.sub_sector || step1.company && step1.company.sector || '';
  const stage = step1.company && step1.company.stage || '';
  const dateStr = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

  const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Footer, PageNumber, BorderStyle } = docxLib;

  const para = (text, opts) => new Paragraph(Object.assign({
    children: [new TextRun({ text: docxSafe(text, 4000), font: 'Montserrat' })]
  }, opts || {}));

  const heading = (text, level) => new Paragraph({
    heading: level || HeadingLevel.HEADING_1,
    spacing: { before: 280, after: 140 },
    children: [new TextRun({ text: docxSafe(text, 200), font: 'Montserrat', bold: true, color: '1a2e31' })]
  });

  const children = [];

  children.push(new Paragraph({
    spacing: { after: 60 },
    children: [new TextRun({ text: 'CLIMATEDOOR', font: 'Montserrat', bold: true, color: 'C89060', size: 22 })]
  }));
  children.push(new Paragraph({
    spacing: { after: 200 },
    border: { bottom: { color: 'C89060', space: 4, style: BorderStyle.SINGLE, size: 6 } },
    children: [
      new TextRun({ text: 'Pre-Call Intelligence  |  ', font: 'Montserrat', color: '5E807B', size: 18 }),
      new TextRun({ text: company + '  |  Generated ' + dateStr, font: 'Montserrat', color: '777777', size: 16 })
    ]
  }));

  children.push(new Paragraph({
    spacing: { after: 200 },
    children: [new TextRun({ text: company, font: 'Montserrat', bold: true, size: 36, color: '1a2e31' })]
  }));
  if (sector || stage) {
    children.push(para([sector, stage].filter(Boolean).join(' / '), { spacing: { after: 200 } }));
  }
  if (description) {
    children.push(para(description, { spacing: { after: 240 } }));
  }

  if (hooksData && Array.isArray(hooksData.hooks) && hooksData.hooks.length > 0) {
    children.push(heading('Top hooks', HeadingLevel.HEADING_2));
    hooksData.hooks.forEach(function(h, i) {
      children.push(new Paragraph({
        spacing: { before: 80, after: 30 },
        children: [
          new TextRun({ text: (i + 1) + '. ', font: 'Montserrat', bold: true, color: 'C89060' }),
          new TextRun({ text: docxSafe(h.headline || '', 800), font: 'Montserrat', bold: true, color: '1a2e31' })
        ]
      }));
      if (h.supporting_detail) {
        children.push(para(h.supporting_detail, { spacing: { after: 120 } }));
      }
    });
  }

  function addSection(title, data, extractor) {
    if (!data) return;
    children.push(heading(title, HeadingLevel.HEADING_2));
    try {
      const items = extractor(data);
      if (!items || items.length === 0) {
        children.push(para('No data.', { spacing: { after: 120 } }));
        return;
      }
      items.forEach(function(it) {
        children.push(new Paragraph({
          spacing: { before: 80, after: 20 },
          children: [new TextRun({ text: docxSafe(it.title, 200), font: 'Montserrat', bold: true })]
        }));
        if (it.detail) children.push(para(it.detail, { spacing: { after: 120 } }));
      });
    } catch (e) {
      children.push(para('Section render failed: ' + e.message, { spacing: { after: 120 } }));
    }
  }

  addSection('Investor matches', step2, function(d) {
    const list = (d && d.investors) || (d && d.matches) || [];
    return list.slice(0, 20).map(function(i) {
      return { title: i.name || i.firm || 'Unnamed', detail: [i.thesis, i.url, i.rationale].filter(Boolean).join(' | ') };
    });
  });
  addSection('Buyer / contact intelligence', step2b, function(d) {
    const list = (d && d.contacts) || (d && d.matches) || [];
    return list.slice(0, 20).map(function(c) {
      return { title: [c.name, c.title].filter(Boolean).join(' / ') || 'Unnamed contact', detail: [c.company, c.email, c.linkedin_url].filter(Boolean).join(' | ') };
    });
  });
  addSection('Grants', step3, function(d) {
    const list = (d && d.grants) || (d && d.matches) || [];
    return list.slice(0, 20).map(function(g) {
      return { title: g.title || g.name || 'Untitled grant', detail: [g.funder, g.amount, g.deadline, g.url].filter(Boolean).join(' | ') };
    });
  });
  addSection('Market signals', step4, function(d) {
    const list = (d && d.signals) || (d && d.matches) || (d && d.events) || [];
    return list.slice(0, 20).map(function(s) {
      return { title: s.title || s.name || 'Signal', detail: [s.summary, s.url, s.date].filter(Boolean).join(' | ') };
    });
  });
  addSection('Experts', step5, function(d) {
    const list = (d && d.experts) || (d && d.matches) || [];
    return list.slice(0, 20).map(function(e) {
      return { title: [e.name, e.title].filter(Boolean).join(' / ') || 'Unnamed', detail: [e.affiliation, e.linkedin_url, e.expertise].filter(Boolean).join(' | ') };
    });
  });

  if (step6) {
    children.push(heading('Synthesis', HeadingLevel.HEADING_2));
    const text = (step6 && step6.synthesis) || (step6 && step6.summary) || JSON.stringify(step6).slice(0, 4000);
    children.push(para(text, { spacing: { after: 200 } }));
  }

  const footer = new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ text: 'Confidential. For internal use.   |   Page ', font: 'Montserrat', size: 14, color: '777777' }),
        new TextRun({ children: [PageNumber.CURRENT], font: 'Montserrat', size: 14, color: '777777' }),
        new TextRun({ text: ' of ', font: 'Montserrat', size: 14, color: '777777' }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Montserrat', size: 14, color: '777777' })
      ]
    })]
  });

  const doc = new Document({
    creator: 'ClimateDoor',
    title: company + ' Playbook',
    styles: { default: { document: { run: { font: 'Montserrat' } } } },
    sections: [{
      properties: { page: { margin: { top: 720, right: 720, bottom: 900, left: 720 } } },
      footers: { default: footer },
      children
    }]
  });

  return Packer.toBuffer(doc);
}

// ---------------------------------------------------------------------------
// CLI-1212 v30 Wave 1a: visual-fidelity PDF via headless Chromium (puppeteer).
// Renders the live playbook URL and captures it 1:1 with dark theme intact.
// Cached to data/<slug>/exports/visual.pdf with 1h TTL.
// Sequential only (lock prevents concurrent renders pushing RAM > 70%).
// ---------------------------------------------------------------------------
const puppeteerLib = require('puppeteer');
const PDF_VISUAL_TTL_MS = parseInt(process.env.PLAYBOOK_PDF_CACHE_TTL_MS || '3600000', 10);
const PDF_VISUAL_PUBLIC_BASE = process.env.PLAYBOOK_PUBLIC_BASE || 'https://www.climatedoor.ai';
let _PDF_VISUAL_LOCK = null;

async function buildVisualPdf(slug, opts) {
  opts = opts || {};
  const exportsDir = path.join(DATA_DIR, slug, 'exports');
  const cachePath = path.join(exportsDir, 'visual.pdf');
  const stampPath = path.join(exportsDir, '.cache-stamp');
  fs.mkdirSync(exportsDir, { recursive: true });

  if (!opts.bust && fs.existsSync(cachePath) && fs.existsSync(stampPath)) {
    const stamp = parseInt(fs.readFileSync(stampPath, 'utf8'), 10) || 0;
    if (Date.now() - stamp < PDF_VISUAL_TTL_MS) {
      return { buffer: fs.readFileSync(cachePath), cached: true, age_ms: Date.now() - stamp };
    }
  }

  while (_PDF_VISUAL_LOCK) {
    await _PDF_VISUAL_LOCK.catch(() => {});
  }
  let unlock;
  _PDF_VISUAL_LOCK = new Promise(r => { unlock = r; });
  let buffer = null;
  try {
    const url = PDF_VISUAL_PUBLIC_BASE + '/playbooks/' + encodeURIComponent(slug) + '/?print_mode=visual';
    const browser = await puppeteerLib.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    });
    try {
      const page = await browser.newPage();
      await page.setViewport({ width: 1280, height: 1800, deviceScaleFactor: 1 });
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.evaluate(() => new Promise(r => setTimeout(r, 2500)));
      try { await page.evaluate(() => { document.body.classList.add('pdf-export'); }); } catch (_) {}
      buffer = await page.pdf({
        format: process.env.PLAYBOOK_PDF_PAGE_FORMAT || 'Letter',
        printBackground: true,
        margin: { top: '0.4in', right: '0.4in', bottom: '0.5in', left: '0.4in' },
        displayHeaderFooter: false
      });
    } finally {
      await browser.close();
    }
    fs.writeFileSync(cachePath, buffer);
    fs.writeFileSync(stampPath, String(Date.now()));
  } finally {
    unlock();
    _PDF_VISUAL_LOCK = null;
  }
  return { buffer, cached: false, age_ms: 0 };
}

function bustVisualPdfCache(slug) {
  const stampPath = path.join(DATA_DIR, slug, 'exports', '.cache-stamp');
  try { fs.unlinkSync(stampPath); } catch (_) {}
}


// ---------------------------------------------------------------------------
// CLI-1193 v27: concurrency semaphore (default 5 simultaneous playbook runs)
// ---------------------------------------------------------------------------
const PLAYBOOK_MAX_CONCURRENT = parseInt(process.env.PLAYBOOK_MAX_CONCURRENT || '5', 10);
let _activeRuns = 0;
const _waitingResolvers = [];

function acquireRunSlot(slug, sendEvent) {
  if (_activeRuns < PLAYBOOK_MAX_CONCURRENT) {
    _activeRuns++;
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    const position = _waitingResolvers.length + 1;
    if (sendEvent) {
      sendEvent('queued', { slug, position, max_concurrent: PLAYBOOK_MAX_CONCURRENT, active: _activeRuns });
    }
    _waitingResolvers.push(() => {
      _activeRuns++;
      resolve(true);
    });
  });
}

function releaseRunSlot() {
  _activeRuns = Math.max(0, _activeRuns - 1);
  const next = _waitingResolvers.shift();
  if (next) next();
}

function semaphoreSnapshot() {
  return { active: _activeRuns, queued: _waitingResolvers.length, max_concurrent: PLAYBOOK_MAX_CONCURRENT };
}



function parseRoute(url, method) {
  // /api/playbooks/:slug/action
  const m = url.match(/^\/api\/playbooks\/([^/]+)\/(.+)$/);
  if (!m) return null;
  return { slug: m[1], action: m[2] };
}

// ---------------------------------------------------------------------------
// Multer setup (for upload endpoint)
// ---------------------------------------------------------------------------
let uploadMiddleware = null;
if (multer) {
  // We'll configure per-request since slug is dynamic
}

function handleMultipart(req, slug) {
  return new Promise((resolve, reject) => {
    if (!multer) return reject(new Error('multer not available'));
    const uploadDir = path.join(DATA_DIR, slug, 'uploads');
    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

    const storage = multer.diskStorage({
      destination: uploadDir,
      filename: (req, file, cb) => {
        const ts = Date.now();
        cb(null, `${ts}-${file.originalname}`);
      },
    });
    const upload = multer({ storage, limits: { fileSize: 20 * 1024 * 1024 } }).single('file');
    // Multer needs a res-like object; provide minimal stub
    const fakeRes = { headersSent: false, setHeader: () => {}, end: () => {}, status: () => fakeRes };
    upload(req, fakeRes, (err) => {
      if (err) {
        log('Multer error: ' + err.message);
        return reject(err);
      }
      log('File uploaded: ' + (req.file ? req.file.originalname : 'none'));
      resolve({ file: req.file, prompt: req.body?.prompt || '' });
    });
  });
}

// ---------------------------------------------------------------------------
// Endpoint handlers
// ---------------------------------------------------------------------------

/** POST /api/playbooks/:slug/edit */
async function handleEdit(slug, body) {
  const { step, path: dotPath, value } = body;
  if (!step || !dotPath || value === undefined) {
    throw new Error('Missing required fields: step, path, value');
  }

  const filePath = stepFile(slug, step);
  const data = readJSON(filePath);
  const fname = path.basename(filePath);

  // Version backup before modifying
  const version = createVersion(slug, 'patch', [fname]);

  // Apply edit
  setByPath(data, dotPath, value);
  writeJSON(filePath, data);

  // Rebuild and deploy
  rebuild(slug);

  return { success: true, version };
}

/** POST /api/playbooks/:slug/prompt */
async function handlePrompt(slug, body) {
  const { prompt, section } = body;
  if (!prompt) throw new Error('Missing required field: prompt');

  const resolved = resolveSection(section);
  const systemPrompt = 'You are editing a ClimateDoor Growth Playbook section. Return ONLY the modified JSON for the section, preserving the exact same structure. Never use em dashes.';

  let sectionData, filePath, fname, dotPath;
  let allStepData = null;

  if (!resolved || resolved.step === 'all') {
    // Full mode: send step6 synthesis data (contains strategy, opportunities, questions, alerts)
    // This is much cheaper than sending all 6 steps and produces more reliable results
    const synthFile = stepFile(slug, 'step6');
    const synthData = readJSON(synthFile);

    const userMsg = `Here is the playbook synthesis data:\n\n${JSON.stringify(synthData, null, 2)}\n\nUser request: ${prompt}\n\nReturn the COMPLETE modified synthesis data as a JSON object with the same top-level keys. Preserve the exact structure.`;
    const result = await callSonnet(systemPrompt, userMsg);
    const parsed = extractJSON(result.text);

    if (!parsed || typeof parsed !== 'object') throw new Error('Could not parse JSON from AI response');

    // Version backup
    const version = createVersion(slug, 'minor', ['step6-synthesis.json'], { prompt, cost: `$${result.cost.toFixed(4)}` });

    // Merge: keep metadata fields, update content fields
    const original = readJSON(synthFile);
    const merged = { ...original, ...parsed };
    // Preserve non-content fields
    merged.company = original.company;
    merged.generated_at = original.generated_at;
    merged.model = original.model;
    merged.token_usage = original.token_usage;

    writeJSON(synthFile, merged);
    rebuild(slug);
    return { success: true, changes: ['step6-synthesis'], cost: `$${result.cost.toFixed(4)}`, version };
  }

  // Specific section
  filePath = path.join(DATA_DIR, slug, resolved.file);
  fname = resolved.file;
  const fileData = readJSON(filePath);

  if (resolved.findBy) {
    // Investor: find by db_id in array
    const arr = getByPath(fileData, resolved.path);
    if (!Array.isArray(arr)) throw new Error(`Path ${resolved.path} is not an array`);
    const idx = arr.findIndex(item => String(item[resolved.findBy]) === String(resolved.findVal));
    if (idx === -1) throw new Error(`Item with ${resolved.findBy}=${resolved.findVal} not found`);
    sectionData = arr[idx];
    dotPath = `${resolved.path}[${idx}]`;
  } else {
    sectionData = getByPath(fileData, resolved.path);
    dotPath = resolved.path;
  }

  if (sectionData === undefined) throw new Error(`Section not found at path: ${resolved.path}`);

  const userMsg = `Here is the current section data:\n\n${JSON.stringify(sectionData, null, 2)}\n\nUser request: ${prompt}\n\nReturn ONLY the modified JSON for this section.`;
  const result = await callSonnet(systemPrompt, userMsg);
  const parsed = extractJSON(result.text);

  // Version backup
  const version = createVersion(slug, 'minor', [fname], { prompt, cost: `$${result.cost.toFixed(4)}` });

  // Apply
  setByPath(fileData, dotPath, parsed);
  writeJSON(filePath, fileData);

  rebuild(slug);
  return { success: true, changes: [section], cost: `$${result.cost.toFixed(4)}`, version };
}

/** POST /api/playbooks/:slug/upload */
async function handleUpload(slug, req) {
  const { file, prompt } = await handleMultipart(req, slug);
  if (!file) throw new Error('No file uploaded');

  // Extract text from file
  let fileText = '';
  const ext = path.extname(file.originalname).toLowerCase();

  if (ext === '.pdf') {
    if (!pdfParse) throw new Error('pdf-parse not available');
    const buf = fs.readFileSync(file.path);
    const pdfData = await pdfParse(buf);
    fileText = pdfData.text;
  } else if (['.txt', '.csv', '.tsv', '.md'].includes(ext)) {
    fileText = fs.readFileSync(file.path, 'utf8');
  } else {
    throw new Error(`Unsupported file type: ${ext}`);
  }

  // Truncate if very long
  if (fileText.length > 50000) fileText = fileText.slice(0, 50000) + '\n[...truncated]';

  // Load current playbook data
  const allStepData = {};
  const steps = ['step1', 'step2', 'step3', 'step4', 'step5', 'step6'];
  for (const s of steps) {
    try {
      allStepData[s] = readJSON(stepFile(slug, s));
    } catch (e) { /* skip */ }
  }

  const systemPrompt = 'You are editing a ClimateDoor Growth Playbook based on an uploaded document. Return a JSON array of patches. Each patch: {"step": "step6", "path": "strategy_pillars.capital.summary", "value": "new text"}. Preserve existing data structure. Never use em dashes.';
  const userMsg = `Here is the current playbook data:\n\n${JSON.stringify(allStepData, null, 2)}\n\nHere is the uploaded document:\n\n${fileText}\n\n${prompt ? `Additional instructions: ${prompt}\n\n` : ''}Return a JSON array of patches to apply.`;

  const result = await callSonnet(systemPrompt, userMsg);
  const patches = extractJSON(result.text);

  if (!Array.isArray(patches)) throw new Error('AI did not return a valid patches array');

  // Track changed files
  const changedFiles = new Set();

  // Version backup (all files that might change)
  const potentialFiles = [...new Set(patches.map(p => {
    try { return path.basename(stepFile(slug, p.step)); } catch (e) { return null; }
  }).filter(Boolean))];
  const version = createVersion(slug, 'minor', potentialFiles, { prompt: prompt || file.originalname, cost: `$${result.cost.toFixed(4)}` });

  // Apply patches
  let applied = 0;
  for (const patch of patches) {
    try {
      const fp = stepFile(slug, patch.step);
      const data = readJSON(fp);
      setByPath(data, patch.path, patch.value);
      writeJSON(fp, data);
      changedFiles.add(patch.step);
      applied++;
    } catch (e) {
      log(`Patch failed: ${JSON.stringify(patch)} - ${e.message}`);
    }
  }

  rebuild(slug);
  return {
    success: true,
    patches_applied: applied,
    changes: [...changedFiles],
    cost: `$${result.cost.toFixed(4)}`,
    version,
  };
}

/** POST /api/playbooks/:slug/add-signal */
async function handleAddSignal(slug, body) {
  const { date, signal, relevance, action_level, source_url, category } = body;
  if (!signal) throw new Error('Missing required field: signal');

  const filePath = stepFile(slug, 'step4');
  const data = readJSON(filePath);
  const fname = path.basename(filePath);

  if (!data.market_signals) data.market_signals = [];

  // Version backup
  const version = createVersion(slug, 'patch', [fname]);

  data.market_signals.push({
    date: date || new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' }),
    signal,
    relevance: relevance || '',
    action_level: action_level || 'watch',
    source_url: source_url || '',
    category: category || 'other',
  });

  writeJSON(filePath, data);
  rebuild(slug);

  return { success: true, version };
}

/** POST /api/playbooks/:slug/remove */
async function handleRemove(slug, body) {
  const { section, index, db_id, name } = body;
  if (!section) throw new Error('Missing required field: section');

  // Section -> step file + array path
  const sectionMap = {
    investor:    { step: 'step2', arrayPath: 'investors' },
    grant:       { step: 'step3', arrayPath: 'direct_grants' },
    signal:      { step: 'step4', arrayPath: 'market_signals' },
    buyer:       { step: 'step4', arrayPath: 'buyer_segments' },
    opportunity: { step: 'step6', arrayPath: 'creative_opportunities' },
    question:    { step: 'step6', arrayPath: 'key_questions' },
    alert:       { step: 'step6', arrayPath: 'alerts' },
    expert:      { step: 'step5', arrayPath: 'expert_matches' },
    indigenous:  { step: 'step4', arrayPath: 'indigenous_opportunities' },
  };

  const mapping = sectionMap[section];
  if (!mapping) throw new Error(`Unknown section: ${section}`);

  const filePath = stepFile(slug, mapping.step);
  const data = readJSON(filePath);
  const fname = path.basename(filePath);
  const arr = getByPath(data, mapping.arrayPath);

  if (!Array.isArray(arr)) throw new Error(`${mapping.arrayPath} is not an array`);

  // Version backup
  const version = createVersion(slug, 'patch', [fname]);

  if (index !== undefined && index !== null) {
    if (index < 0 || index >= arr.length) throw new Error(`Index ${index} out of range (0-${arr.length - 1})`);
    arr.splice(index, 1);
  } else if (db_id) {
    const idx = arr.findIndex(item => String(item.db_id) === String(db_id));
    if (idx === -1) throw new Error(`No item with db_id=${db_id} found`);
    arr.splice(idx, 1);
  } else if (name) {
    const idx = arr.findIndex(item => item.name === name);
    if (idx === -1) throw new Error(`No item with name="${name}" found`);
    arr.splice(idx, 1);
  } else {
    throw new Error('Must provide index, db_id, or name to identify item to remove');
  }

  setByPath(data, mapping.arrayPath, arr);
  writeJSON(filePath, data);
  rebuild(slug);

  return { success: true, version };
}

/** GET /api/playbooks/:slug/versions */
async function handleVersions(slug) {
  const vLog = readVersionLog(slug);
  return { success: true, current: vLog.current, versions: vLog.versions };
}

/** POST /api/playbooks/:slug/rollback */
async function handleRollback(slug, body) {
  const { version } = body;
  if (!version) throw new Error('Missing required field: version');

  const vDir = ensureVersionDir(slug);
  const snapDir = path.join(vDir, version);

  if (!fs.existsSync(snapDir)) throw new Error(`Version ${version} not found`);

  // Read metadata to know which files were saved
  const metaFile = path.join(snapDir, 'metadata.json');
  let files;
  if (fs.existsSync(metaFile)) {
    const meta = readJSON(metaFile);
    files = meta.changed_files || [];
  } else {
    // Fallback: copy all JSON files from snapshot
    files = fs.readdirSync(snapDir).filter(f => f.endsWith('.json') && f !== 'metadata.json');
  }

  // Restore files
  for (const f of files) {
    const src = path.join(snapDir, f);
    const dest = path.join(DATA_DIR, slug, f);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, dest);
      log(`Restored ${f} from ${version}`);
    }
  }

  // Update version log
  const vLog = readVersionLog(slug);
  vLog.current = version;
  vLog.versions.push({
    version: version + '-rollback',
    timestamp: new Date().toISOString(),
    change_type: 'rollback',
    prompt_text: `Rolled back to ${version}`,
    cost: null,
    changed_files: files,
  });
  writeVersionLog(slug, vLog);

  rebuild(slug);
  return { success: true, restored: version, files };
}

// ---------------------------------------------------------------------------
// Tag normalization helpers (ICP v7 picklist)
// ---------------------------------------------------------------------------
function normalizeTRL(raw) {
  const s = String(raw || '').trim();
  const m = s.match(/(\d+)/);
  if (!m) return '';
  const n = parseInt(m[1]);
  if (n <= 4) return 'TRL 1-4 (Concept / Prototype)';
  if (n <= 6) return 'TRL 5-6 (Validation / Demo)';
  if (n === 7) return 'TRL 7 (Pilot)';
  if (n === 8) return 'TRL 8 (Market Entry)';
  if (n >= 9) return 'TRL 9 (Scaling Up)';
  return '';
}

function normalizeStage(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  const lo = s.toLowerCase().replace(/[\s-]+/g, ' ').trim();
  if (/^pre\s*seed/.test(lo)) return 'Pre-seed';
  if (/^pre\s*series\s*a/.test(lo)) return 'Seed';
  if (/^seed/.test(lo)) return 'Seed';
  if (/^series\s*a/.test(lo) || /^early/.test(lo)) return 'Series A';
  if (/^series\s*b/.test(lo)) return 'Series B';
  if (/^series\s*[c-z]/.test(lo) || /^late\s*stage/.test(lo)) return 'Series C+';
  if (/^growth/.test(lo)) return 'Series B';
  if (/^bridge/.test(lo)) return 'Bridge';
  if (/^ipo/.test(lo)) return 'IPO';
  if (/^pub\s*co/.test(lo) || /^public/.test(lo)) return 'PubCo';
  if (/^mezzanine/.test(lo)) return 'Mezzanine';
  // Return cleaned original if no mapping
  return s.split(/[\s—–/(]/)[0].trim();
}

function normalizeSector(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  const lo = s.toLowerCase();
  const map = [
    [/ag|food|agri/i, 'Ag & Food'],
    [/building|smart\s*cit/i, 'Buildings & Smart Cities'],
    [/carbon|ccs|ccus|dac/i, 'Carbon'],
    [/circular/i, 'Circular Economy'],
    [/clean\s*ind|adv.*manuf|industrial\s*decarb/i, 'Clean Industry / Advanced Manufacturing'],
    [/climate\s*int|climate\s*soft|climate\s*tech.*soft/i, 'Climate Intelligence & Software'],
    [/digital/i, 'Digital Services'],
    [/energy|storage|battery|solar|wind|grid|renew/i, 'Energy & Storage'],
    [/financ|policy|market|carbon\s*market/i, 'Finance Policy & Markets'],
    [/nature|community|nbs|ecosystem/i, 'Nature-based & Community Solutions'],
    [/transport|mobil|ev\b|vehicle/i, 'Transportation'],
    [/construct|data\s*cent|cool/i, 'Buildings & Smart Cities'],
    [/mining|mineral|critical\s*min/i, 'Clean Industry / Advanced Manufacturing'],
    [/sovereign|ai\s*infra|deep\s*tech/i, 'Climate Intelligence & Software'],
    [/water|decontam|wastewater|remediat/i, 'Water & Decontamination'],
  ];
  for (const [re, label] of map) {
    if (re.test(s)) return label;
  }
  return s; // Keep original if no mapping found
}

function truncateDescription(text) {
  if (!text) return '';
  // Find first sentence ending
  const m = text.match(/^[^.!?]+[.!?]/);
  let result = m ? m[0].trim() : text;
  // Cap at 120 chars even if the first sentence is long
  if (result.length > 120) {
    // Try to break at a word boundary
    result = result.substring(0, 117).replace(/\s+\S*$/, '') + '...';
  }
  return result;
}

function determinePhase(slug, source) {
  if (source === 'radar') return 'Phase 1';
  const hasStep6 = fs.existsSync(path.join(DATA_DIR, slug, 'step6-synthesis.json'));
  const hasStep4 = fs.existsSync(path.join(DATA_DIR, slug, 'step4-market.json'));
  if (hasStep6) return 'Full Playbook';
  if (hasStep4) return 'Phase 2';
  return 'Phase 1';
}

// ---------------------------------------------------------------------------
// List all playbooks (scans deploy dir + reads step1 metadata)
// ---------------------------------------------------------------------------
function handleList() {
  const playbooks = [];
  const dirs = fs.readdirSync(DEPLOY_ROOT).filter(d => {
    if (d === 'editor') return false;
    const dp = path.join(DEPLOY_ROOT, d);
    return fs.statSync(dp).isDirectory() && fs.existsSync(path.join(dp, 'index.html'));
  });

  for (const slug of dirs) {
    const entry = { slug, name: slug, source: 'static' };
    // Try to load step1-company.json for rich metadata
    const step1Path = path.join(DATA_DIR, slug, 'step1-company.json');
    if (fs.existsSync(step1Path)) {
      try {
        const s1 = readJSON(step1Path);
        const c = s1.company || {};
        entry.name = c.name || slug;
        entry.description = truncateDescription(c.description || '');
        entry.sector = normalizeSector(c.sector || '');
        entry.stage = normalizeStage(c.stage || '');
        entry.trl = normalizeTRL(String(c.trl || ''));
        entry.hq = (c.geography && c.geography.hq) || '';
        entry.source = 'pipeline';
      } catch (e) { /* use defaults */ }
    }

    // Count all discovery types from step data files
    const metrics = { opportunities: 0, investors: 0, buyers: 0, experts: 0, grants: 0, signals: 0, indigenous: 0, events: 0 };
    try {
      const s2 = readJSON(path.join(DATA_DIR, slug, 'step2-investors.json'));
      metrics.investors = (s2.investors || []).length;
    } catch (e) {}
    try {
      const s3 = readJSON(path.join(DATA_DIR, slug, 'step3-grants.json'));
      metrics.grants = (s3.direct_grants || []).length;
    } catch (e) {}
    try {
      const s4 = readJSON(path.join(DATA_DIR, slug, 'step4-market.json'));
      metrics.buyers = (s4.buyer_segments || []).length;
      metrics.signals = (s4.market_signals || []).length;
      metrics.indigenous = (s4.indigenous_opportunities || []).length;
      metrics.events = (s4.conference_targets || s4.events || []).length;
    } catch (e) {}
    try {
      const s5 = readJSON(path.join(DATA_DIR, slug, 'step5-experts.json'));
      metrics.experts = (s5.expert_matches || []).length;
    } catch (e) {}
    try {
      const s6 = readJSON(path.join(DATA_DIR, slug, 'step6-synthesis.json'));
      metrics.opportunities = (s6.creative_opportunities || []).length;
    } catch (e) {}

    entry.metrics = metrics;
    entry.totalDiscoveries = Object.values(metrics).reduce((a, b) => a + b, 0);
    entry.phase = determinePhase(slug, entry.source);

    // CLI-1194: surface last_modified so the frontend can sort newest-first.
    // Use the freshest mtime across step1-company.json, the slug data dir,
    // and the deployed slug folder. ISO string for easy lexicographic sort.
    let mtimeMs = 0;
    try {
      const t = fs.statSync(path.join(DATA_DIR, slug, 'step1-company.json')).mtimeMs;
      if (t > mtimeMs) mtimeMs = t;
    } catch (_) {}
    try {
      const t = fs.statSync(path.join(DATA_DIR, slug)).mtimeMs;
      if (t > mtimeMs) mtimeMs = t;
    } catch (_) {}
    try {
      const t = fs.statSync(path.join(DEPLOY_ROOT, slug)).mtimeMs;
      if (t > mtimeMs) mtimeMs = t;
    } catch (_) {}
    if (mtimeMs > 0) entry.last_modified = new Date(mtimeMs).toISOString();

    playbooks.push(entry);
  }

  // -------------------------------------------------------------------------
  // RADAR pages — scan JSON data dir, deduplicate, merge
  // -------------------------------------------------------------------------
  try {
    const pipelineNames = new Set(playbooks.map(p =>
      p.name.toLowerCase().replace(/\s+(design|solutions|technologies|inc|ltd|corp)\.?$/i, '').trim()
    ));

    const radarFiles = fs.readdirSync(RADAR_DATA_DIR).filter(f => f.endsWith('.json'));
    const radarMap = new Map();

    for (const file of radarFiles) {
      try {
        const data = readJSON(path.join(RADAR_DATA_DIR, file));
        const name = (data.company && data.company.name) || file.replace('.json', '');
        const norm = name.toLowerCase().replace(/\s+(design|solutions|technologies|inc|ltd|corp)\.?$/i, '').trim();
        const updated = data.lastUpdated || data.createdAt || '';
        const existing = radarMap.get(norm);
        if (!existing || updated > existing.updated) {
          radarMap.set(norm, { file, data, updated });
        }
      } catch (e) { /* skip bad files */ }
    }

    for (const [norm, { file, data }] of radarMap) {
      if (pipelineNames.has(norm)) continue;

      const c = data.company || {};
      const slug = file.replace('.json', '').replace(/-data$/, '');

      // Count all metric types
      const investors = Array.isArray(data.investors) ? data.investors.length : 0;
      const gSecured = ((data.grants || {}).secured || []).length;
      const gAdditional = ((data.grants || {}).additional || []).length;
      const buyers = Array.isArray(data.buyers) ? data.buyers.length : 0;
      const signals = Array.isArray(data.signals) ? data.signals.length : 0;
      const events = Array.isArray(data.events) ? data.events.length : 0;
      const indigenous = Array.isArray(data.indigenous) ? data.indigenous.length : 0;
      let experts = 0;
      if (data.experts && typeof data.experts === 'object' && !Array.isArray(data.experts)) {
        for (const arr of Object.values(data.experts)) {
          if (Array.isArray(arr)) experts += arr.length;
        }
      }
      const opportunities = Array.isArray(data.opportunities) ? data.opportunities.length : 0;

      const metrics = {
        opportunities,
        investors,
        buyers,
        experts,
        grants: gSecured + gAdditional,
        signals,
        indigenous,
        events,
      };

      const totalDiscoveries = Object.values(metrics).reduce((a, b) => a + b, 0);

      // Determine phase for RADAR based on data completeness
      let phase = 'Phase 1';
      const dataPoints = [investors, buyers, experts, gSecured + gAdditional, signals].filter(n => n > 0).length;
      if (dataPoints >= 4) phase = 'Phase 2';

      playbooks.push({
        slug,
        name: c.name || slug,
        description: truncateDescription(c.tagline || ''),
        sector: normalizeSector(c.sector || ''),
        stage: normalizeStage(c.stage || ''),
        trl: normalizeTRL(String(c.trl || '')),
        hq: c.location || '',
        source: 'radar',
        phase,
        metrics,
        totalDiscoveries,
        // CLI-1194: prefer JSON-provided timestamp; fall back to file mtime.
        last_modified: (function() {
          if (data.lastUpdated) return data.lastUpdated;
          if (data.createdAt) return data.createdAt;
          try { return fs.statSync(path.join(RADAR_DATA_DIR, file)).mtime.toISOString(); }
          catch (_) { return null; }
        })(),
      });
    }
  } catch (e) {
    log(`RADAR scan error: ${e.message}`);
  }

  return { success: true, playbooks };
}

// ---------------------------------------------------------------------------
// CLI-1209 (v25 Wave 2): Hook ranker. Calls Sonnet to extract the 3 to 5 most
// attention-grabbing signals from a playbook. Output saved to data/<slug>/hooks.json.
// ---------------------------------------------------------------------------
const HOOK_COST_CEILING_USD = 0.15;

function readSafeJSON(p) {
  try { return readJSON(p); } catch (_) { return null; }
}

async function rankHooks(slug) {
  const dataDir = path.join(DATA_DIR, slug);
  if (!fs.existsSync(dataDir)) {
    throw new Error(`No playbook data for ${slug}`);
  }

  const ctx = {};
  const s1 = readSafeJSON(path.join(dataDir, 'step1-company.json'));
  if (s1 && s1.company) {
    const c = s1.company;
    ctx.company = {
      name: c.name, tagline: c.tagline, sector: c.sector, stage: c.stage, trl: c.trl,
      website: c.website || c.url, location: c.location || (c.geography && c.geography.hq),
      summary: c.summary || c.description,
      funding_to_date: c.funding_to_date, last_round: c.last_round,
      team_size: c.team_size, founded: c.founded
    };
  }
  const s2 = readSafeJSON(path.join(dataDir, 'step2-investors.json'));
  if (s2) ctx.top_investors = (s2.investors || []).slice(0, 5).map(i => ({
    name: i.name, type: i.type, fit_rationale: i.fit_rationale || i.why
  }));
  const s3 = readSafeJSON(path.join(dataDir, 'step3-grants.json'));
  if (s3) ctx.top_grants = (s3.direct_grants || []).slice(0, 5).map(g => ({
    name: g.name, deadline: g.deadline, amount: g.amount, fit: g.fit_rationale || g.why
  }));
  const s4 = readSafeJSON(path.join(dataDir, 'step4-market.json'));
  if (s4) {
    ctx.market_signals = (s4.market_signals || []).slice(0, 6).map(m => ({
      headline: m.headline || m.title, source: m.source, date: m.date, summary: m.summary
    }));
    ctx.indigenous_opps = (s4.indigenous_opportunities || []).slice(0, 3);
    ctx.events = (s4.conference_targets || s4.events || []).slice(0, 3).map(e => ({
      name: e.name, date: e.date, location: e.location
    }));
  }
  const s5 = readSafeJSON(path.join(dataDir, 'step5-experts.json'));
  if (s5) ctx.expert_matches = (s5.expert_matches || []).slice(0, 5).map(e => ({
    name: e.name, expertise: e.expertise, why: e.fit_rationale || e.why
  }));
  const s6 = readSafeJSON(path.join(dataDir, 'step6-synthesis.json'));
  if (s6) {
    ctx.creative_opportunities = (s6.creative_opportunities || []).slice(0, 5);
    ctx.alerts = s6.alerts || [];
  }

  const systemPrompt = `You are a senior climate-tech business development strategist for ClimateDoor. Read the playbook signals and return the 3 to 5 most attention-grabbing hooks ranked by their power to make a busy reader (potential investor, buyer, or partner) want to know more in the first 10 seconds.\n\nHook rules:\n- Each hook is 1 to 2 sentences. No more.\n- Action-oriented voice. Lead with the strongest concrete fact.\n- Include a source attribution inline (the section the data came from).\n- Forbidden: em dashes (use commas, periods, or parentheses), hedging words like "might", "could", "potentially", "perhaps", generic phrases like "innovative solution".\n- Pull the most-recent-and-most-specific signal in each category before generic ones.\n\nHook type categories: funding, hiring, product, press, icp, transcript, network, climate.\n\nOutput ONLY a valid JSON array, nothing else, no markdown fences. Schema:\n[{"rank": 1, "hook_type": "funding", "headline": "...", "supporting_detail": "...", "source_section": "..."}]`;

  const userContent = `Company name: ${(ctx.company && ctx.company.name) || slug}\n\nFull playbook signals (top entries per category):\n${JSON.stringify(ctx, null, 2)}\n\nReturn 3 to 5 hooks ranked by power.`;

  const { text, cost, inputTokens, outputTokens } = await callSonnet(systemPrompt, userContent);
  if (cost > HOOK_COST_CEILING_USD) {
    log(`[HOOKS] WARN ${slug} cost ${cost.toFixed(3)} exceeded ceiling ${HOOK_COST_CEILING_USD}`);
  }
  let hooks;
  try {
    hooks = extractJSON(text);
  } catch (e) {
    log(`[HOOKS] ${slug} JSON parse failed; raw length ${text.length}`);
    throw new Error(`Sonnet output not parseable as JSON: ${e.message}`);
  }
  if (!Array.isArray(hooks)) throw new Error('Sonnet output is not an array');

  // Hard guard against em dashes
  hooks.forEach(h => {
    ['headline', 'supporting_detail', 'source_section'].forEach(k => {
      if (typeof h[k] === 'string') h[k] = h[k].replace(/[—–]/g, ',');
    });
  });

  const payload = {
    slug,
    generated_at: new Date().toISOString(),
    model: 'claude-sonnet-4-6',
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: cost,
    hooks,
  };
  fs.writeFileSync(path.join(dataDir, 'hooks.json'), JSON.stringify(payload, null, 2));
  log(`[HOOKS] ${slug} ranked ${hooks.length} hooks at $${cost.toFixed(4)}`);
  return payload;
}

function readHooksFor(slug) {
  const p = path.join(DATA_DIR, slug, 'hooks.json');
  if (!fs.existsSync(p)) return null;
  return readSafeJSON(p);
}

// ---------------------------------------------------------------------------
// CLI-1200 (v24): in-memory tracker for in-flight playbook generations.
// Populated at handleCreate start, updated on every sendEvent, cleared on
// complete/error/disconnect. Enables list-level "running" badge so the user
// keeps visibility even after closing the modal.
// ---------------------------------------------------------------------------
const runningPlaybooks = new Map();

function trackRunningStart(slug, company_name) {
  runningPlaybooks.set(slug, {
    slug,
    company_name: company_name || slug,
    started_at: new Date().toISOString(),
    current_step: 0,
    current_label: 'Initializing',
    last_event_at: new Date().toISOString(),
  });
}

function trackRunningEvent(slug, eventType, data) {
  const entry = runningPlaybooks.get(slug);
  if (!entry) return;
  entry.last_event_at = new Date().toISOString();
  if (eventType === 'status' && data && typeof data.step !== 'undefined') {
    entry.current_step = data.step;
    if (data.label) entry.current_label = data.label;
  } else if (eventType === 'step_done' && data && typeof data.step !== 'undefined') {
    entry.current_step = data.step;
    entry.current_label = `Step ${data.step} complete`;
  }
}

function trackRunningEnd(slug) {
  runningPlaybooks.delete(slug);
  // CLI-1193 v27: release semaphore slot. Idempotent if no slot was held.
  releaseRunSlot();
}

function handleRunning() {
  const running = [];
  for (const [, entry] of runningPlaybooks) {
    running.push({
      slug: entry.slug,
      company_name: entry.company_name,
      started_at: entry.started_at,
      current_step: entry.current_step,
      current_label: entry.current_label,
      last_event_at: entry.last_event_at,
    });
  }
  return { success: true, running };
}

// ---------------------------------------------------------------------------
// CLI-1192: lightweight search for typeahead-while-filling on the new-playbook
// modal. Scans DEPLOY_ROOT for slug folders, reads step1-company.json (lazily)
// for richer name/url/sector match, returns top N substring matches.
// Avoids re-running handleList's heavy metrics aggregation.
// ---------------------------------------------------------------------------
function handleSearch(q, limit) {
  q = (q || '').trim().toLowerCase();
  if (!q || q.length < 2) return { success: true, results: [] };

  const results = [];
  let dirs = [];
  try {
    dirs = fs.readdirSync(DEPLOY_ROOT).filter(d => {
      if (d === 'editor') return false;
      try {
        const dp = path.join(DEPLOY_ROOT, d);
        return fs.statSync(dp).isDirectory() && fs.existsSync(path.join(dp, 'index.html'));
      } catch (_) { return false; }
    });
  } catch (e) {
    return { success: true, results: [] };
  }

  for (const slug of dirs) {
    let name = slug;
    let url = '';
    let sector = '';
    let hq = '';
    let lastRun = null;

    const step1Path = path.join(DATA_DIR, slug, 'step1-company.json');
    if (fs.existsSync(step1Path)) {
      try {
        const s1 = readJSON(step1Path);
        const c = s1.company || {};
        name = c.name || slug;
        url = c.website || c.url || '';
        sector = c.sector || '';
        hq = (c.geography && c.geography.hq) || c.location || '';
        const stat = fs.statSync(step1Path);
        lastRun = stat.mtime.toISOString();
      } catch (_) {}
    } else {
      try {
        const stat = fs.statSync(path.join(DEPLOY_ROOT, slug));
        lastRun = stat.mtime.toISOString();
      } catch (_) {}
    }

    const haystack = [slug, name, url, sector, hq].join(' ').toLowerCase();
    if (!haystack.includes(q)) continue;

    // Score: exact-name and slug-prefix beat substring; recent beats stale.
    let score = 0;
    if (name.toLowerCase() === q) score += 1000;
    if (slug.toLowerCase().startsWith(q)) score += 200;
    if (name.toLowerCase().startsWith(q)) score += 150;
    if (haystack.indexOf(q) >= 0) score += 50;
    if (lastRun) {
      const ageDays = (Date.now() - new Date(lastRun).getTime()) / 86400000;
      score += Math.max(0, 30 - ageDays); // recent ~+30, year-old ~0
    }

    results.push({ slug, name, url, sector, hq, last_run: lastRun, score });
  }

  results.sort((a, b) => b.score - a.score);
  const top = results.slice(0, limit).map(r => {
    const out = { slug: r.slug, name: r.name, url: r.url, last_run: r.last_run, source: 'pipeline' };
    if (r.sector) out.sector = r.sector;
    if (r.hq) out.hq = r.hq;
    return out;
  });
  return { success: true, results: top };
}

// ---------------------------------------------------------------------------
// Create new playbook (full pipeline, SSE progress)
// ---------------------------------------------------------------------------
const STEP_SCRIPTS = [
  { num: 1, label: 'Company Research', script: 'step1_company_research.py' },
  { num: 2, label: 'Investor Matching', script: 'step2_investor_matching.py' },
  { num: '2b', label: 'Apollo Contacts', script: 'step2b_apollo_contacts.py' },
  { num: 3, label: 'Grant Scanning', script: 'step3_grant_scanning.py' },
  { num: 4, label: 'Market Intelligence', script: 'step4_market_intelligence.py' },
  { num: 5, label: 'Expert Matching', script: 'step5_expert_matching.py' },
  { num: 6, label: 'Strategic Synthesis', script: 'step6_synthesis.py' },
  { num: 7, label: 'HTML Assembly', script: 'step7_assemble.py' },
];

/**
 * Skeleton data for steps that fail — allows downstream steps to proceed.
 */
const STEP_SKELETONS = {
  '2b': { file: 'step2b-contacts.json', data: { buyers: { concentric: { scanned: 0, targeted: 0, previewed: 0 }, segments: [], contacts: [] }, investors: { concentric: { scanned: 0, targeted: 0, previewed: 0 }, contacts: [] }, hubspot_field_mapping: {}, generated_at: '', model: 'claude-sonnet-4-6', credits_consumed: 0 } },
  3: { file: 'step3-grants.json', data: { direct_grants: [], grants_as_bd: [], new_programs_for_sophie: [] } },
  4: { file: 'step4-market.json', data: { buyer_segments: [], market_signals: [], competitive_landscape: [], conference_targets: [], indigenous_opportunities: [], sector_temperature: { rating: 'unknown', evidence: [] } } },
  5: { file: 'step5-experts.json', data: { expert_matches: [], growth_pod_assignments: [] } },
  6: { file: 'step6-synthesis.json', data: { strategy_pillars: { capital: { summary: '' }, grants: { summary: '' }, sales: { summary: '' }, signals: { summary: '' } }, creative_opportunities: [], key_questions: [], alerts: [], competitive_position: { defensibility_factors: [] } } },
};

function handleCreateMultipart(req) {
  return new Promise((resolve, reject) => {
    if (!multer) return reject(new Error('multer not available'));
    // Use temp dir first, we'll move files after deriving slug
    const tmpDir = path.join(DATA_DIR, '_tmp_create_' + Date.now());
    if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });

    const storage = multer.diskStorage({
      destination: tmpDir,
      filename: (req, file, cb) => cb(null, file.originalname),
    });
    const upload = multer({ storage, limits: { fileSize: 20 * 1024 * 1024 } }).array('files', 10);
    const fakeRes = { headersSent: false, setHeader: () => {}, end: () => {}, status: () => fakeRes };
    upload(req, fakeRes, (err) => {
      if (err) {
        try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
        return reject(err);
      }
      resolve({ files: req.files || [], fields: req.body || {}, tmpDir });
    });
  });
}

async function handleCreate(req, res) {
  let body, uploadedFiles = [], tmpDir = null;
  const contentType = (req.headers['content-type'] || '').toLowerCase();

  if (contentType.includes('multipart/form-data')) {
    // Handle multipart form data (with file uploads)
    const result = await handleCreateMultipart(req);
    uploadedFiles = result.files;
    tmpDir = result.tmpDir;
    body = result.fields;
    log(`[CREATE] Multipart: ${uploadedFiles.length} files, fields: ${JSON.stringify(body)}`);
  } else {
    body = await parseBody(req);
  }

  const { company_name, website_url, slug: requestedSlug, notes } = body;
  if (!company_name || !website_url) {
    if (tmpDir) try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
    return sendJSON(res, 400, { error: 'company_name and website_url are required' });
  }

  // Derive slug
  const slug = requestedSlug || company_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const dataDir = path.join(DATA_DIR, slug);

  if (fs.existsSync(dataDir) && fs.existsSync(path.join(dataDir, 'step1-company.json'))) {
    if (tmpDir) try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
    return sendJSON(res, 409, { error: `Playbook "${slug}" already exists` });
  }

  // Ensure data directory exists and move uploaded files + save notes
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  if (tmpDir && uploadedFiles.length > 0) {
    for (const f of uploadedFiles) {
      const dest = path.join(dataDir, f.originalname);
      fs.renameSync(f.path, dest);
      log(`[CREATE] Saved uploaded file: ${f.originalname} -> ${dest}`);
    }
    try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
  } else if (tmpDir) {
    try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
  }

  if (notes && notes.trim()) {
    fs.writeFileSync(path.join(dataDir, 'notes.txt'), notes.trim(), 'utf8');
    log(`[CREATE] Saved notes.txt for ${slug}`);
  }

  // SSE headers
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*',
  });

  // CLI-1200: register run + cleanup on client disconnect.
  trackRunningStart(slug, company_name);
  req.on('close', () => {
    if (runningPlaybooks.has(slug)) {
      const entry = runningPlaybooks.get(slug);
      // Only purge if pipeline never completed; otherwise complete/error already cleared it.
      if (entry && entry.current_step < 7) {
        log(`[CREATE] Client disconnected mid-run for ${slug} at step ${entry.current_step}; clearing tracker entry`);
        trackRunningEnd(slug);
      }
    }
  });

  function sendEvent(event, data) {
    trackRunningEvent(slug, event, data);
    if (event === 'complete' || event === 'error') trackRunningEnd(slug);
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  }

  sendEvent('status', { step: 0, label: 'Initializing', slug });

  // CLI-1193 v27: acquire run slot. Sends 'queued' SSE event if at capacity.
  let _wasQueued = false;
  try {
    _wasQueued = await acquireRunSlot(slug, sendEvent);
    if (_wasQueued) {
      sendEvent('status', { step: 0, label: 'Slot acquired, starting now', slug });
    }
  } catch (slotErr) {
    sendEvent('error', { step: 0, message: 'Slot acquisition failed: ' + slotErr.message });
    return;
  }

  // Ensure data directory
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  const scriptsDir = path.join(SKILL_ROOT, 'scripts');
  const skippedSteps = [];
  let hardFail = false;

  for (const step of STEP_SCRIPTS) {
    sendEvent('status', { step: step.num, label: `Running Step ${step.num}: ${step.label}...`, slug });
    log(`[CREATE] Step ${step.num} (${step.label}) for ${slug}`);

    try {
      const args = step.num === 1
        ? [path.join(scriptsDir, step.script), company_name, website_url, slug]
        : [path.join(scriptsDir, step.script), slug];

      await new Promise((resolve, reject) => {
        const stepTimeout = 900000; // 15 minutes per step
        const proc = spawn('python3', args, {
          cwd: SKILL_ROOT,
          env: { ...process.env, ANTHROPIC_API_KEY, APOLLO_API_KEY: process.env.APOLLO_API_KEY || '' },
          timeout: stepTimeout,
        });

        let stdout = '', stderr = '';
        proc.stdout.on('data', d => { stdout += d; });
        proc.stderr.on('data', d => { stderr += d; });
        proc.on('close', (code, signal) => {
          if (signal === 'SIGTERM') {
            const msg = `Step ${step.num} timed out after ${stepTimeout / 1000}s`;
            log(`[CREATE] ${msg}. Last stdout: ${stdout.slice(-300)}`);
            reject(new Error(msg));
          } else if (code !== 0) {
            const errTail = stderr.slice(-500) || stdout.slice(-300) || '(no output)';
            log(`[CREATE] Step ${step.num} failed (exit ${code}): ${errTail}`);
            reject(new Error(`Step ${step.num} failed (exit ${code}): ${errTail.slice(-200)}`));
          } else {
            log(`[CREATE] Step ${step.num} complete for ${slug}`);
            resolve();
          }
        });
        proc.on('error', (err) => {
          log(`[CREATE] Step ${step.num} spawn error: ${err.message}`);
          reject(err);
        });
      });

      sendEvent('step_done', { step: step.num, label: step.label });
    } catch (err) {
      // Step 1 is a hard requirement — can't build anything without company data
      if (step.num === 1) {
        hardFail = true;
        sendEvent('error', { step: step.num, message: err.message });
        break;
      }

      // For steps 2-7: log, write skeleton data if available, continue
      const reason = err.message || 'unknown error';
      log(`[CREATE] Step ${step.num} FAILED for ${slug}: ${reason}`);
      skippedSteps.push(step.num);
      sendEvent('step_skipped', { step: step.num, label: step.label, message: `Failed: ${reason.slice(0, 200)}` });

      // Write skeleton data so downstream steps can proceed
      const skeleton = STEP_SKELETONS[step.num];
      if (skeleton) {
        const skelPath = path.join(dataDir, skeleton.file);
        if (!fs.existsSync(skelPath)) {
          log(`[CREATE] Writing skeleton data for step ${step.num}`);
          writeJSON(skelPath, skeleton.data);
          log(`[CREATE] Wrote skeleton data for step ${step.num}: ${skeleton.file}`);
        }
      }
    }
  }

  if (!hardFail) {
    // Deploy: copy assembled HTML to web root
    const deployDir = path.join(DEPLOY_ROOT, slug);
    if (!fs.existsSync(deployDir)) fs.mkdirSync(deployDir, { recursive: true });

    const possibleSources = [
      path.join(dataDir, 'playbook.html'),
      path.join(SKILL_ROOT, 'output', slug, 'index.html'),
    ];
    let deployed = false;
    for (const src of possibleSources) {
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, path.join(deployDir, 'index.html'));
        deployed = true;
        break;
      }
    }

    // If step7 assembly also failed, check if there is at least an index.html
    if (!deployed && fs.existsSync(path.join(deployDir, 'index.html'))) {
      deployed = true;
    }

    if (deployed || skippedSteps.length < 6) {
      sendEvent('complete', { slug, url: `/playbooks/${slug}/`, skipped: skippedSteps });
      log(`[CREATE] Pipeline complete for ${slug} (skipped steps: ${skippedSteps.join(', ') || 'none'})`);
    } else {
      sendEvent('error', { step: 0, message: 'Too many steps failed. Playbook could not be assembled.' });
    }
  }

  res.end();
}

// ---------------------------------------------------------------------------
// HTTP Server
// ---------------------------------------------------------------------------
const server = http.createServer(async (req, res) => {
  // CLI-235 basic auth (shared realm ClimateDoor)
  const _authPublic = req.url === '/health' || req.url === '/api/health' || (req.url && req.url.startsWith('/health/')) || (req.url && /^(?:\/playbooks)?\/share\/[A-Za-z0-9_-]{16,}(?:\?|$)/.test(req.url));
  if (!_authPublic) {
    const _ah = req.headers.authorization || '';
    const _parts = _ah.split(' ');
    let _ok = false;
    if (_parts[0] === 'Basic' && _parts[1]) {
      const _dec = Buffer.from(_parts[1], 'base64').toString('utf8');
      const _sep = _dec.indexOf(':');
      const _u = _dec.slice(0, _sep);
      const _p = _dec.slice(_sep + 1);
      if (_u === process.env.AUTH_USER && _p === process.env.AUTH_PASS) _ok = true;
    }
    if (!_ok) {
      res.writeHead(401, { 'WWW-Authenticate': 'Basic realm="ClimateDoor"' });
      return res.end('Authentication required');
    }
  }

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    });
    return res.end();
  }

  const parsedUrl = new URL(req.url, `http://localhost:${PORT}`);

  // Special routes (not slug-based)
  if (parsedUrl.pathname === '/api/playbooks/_list' && req.method === 'GET') {
    log('GET /api/playbooks/_list');
    try {
      return sendJSON(res, 200, handleList());
    } catch (err) {
      log(`ERROR: ${err.message}`);
      return sendJSON(res, 500, { error: err.message });
    }
  }

  // CLI-1209 (v25 Wave 2): hook ranker endpoints.
  // GET  /api/playbooks/<slug>/hooks            -> read existing hooks.json or 404
  // POST /api/playbooks/<slug>/hooks/regenerate -> Sonnet call + write + return
  {
    const hookGetMatch = parsedUrl.pathname.match(/^\/api\/playbooks\/([a-z0-9-]+)\/hooks$/i);
    if (hookGetMatch && req.method === 'GET') {
      const slug = hookGetMatch[1];
      log(`GET /api/playbooks/${slug}/hooks`);
      const data = readHooksFor(slug);
      if (!data) return sendJSON(res, 404, { error: `No hooks for ${slug}; trigger regenerate first` });
      return sendJSON(res, 200, data);
    }
    const hookRegenMatch = parsedUrl.pathname.match(/^\/api\/playbooks\/([a-z0-9-]+)\/hooks\/regenerate$/i);
    if (hookRegenMatch && req.method === 'POST') {
      const slug = hookRegenMatch[1];
      log(`POST /api/playbooks/${slug}/hooks/regenerate`);
      try {
        const result = await rankHooks(slug);
        return sendJSON(res, 200, result);
      } catch (err) {
        log(`ERROR rankHooks: ${err.message}`);
        return sendJSON(res, 500, { error: err.message });
      }
    }
  }

  
  // CLI-1212 v27: shareable token endpoints.
  // POST /api/playbooks/<slug>/export/share -> create token + return url
  // GET  /playbooks/share/<token>           -> validate, increment, redirect to /playbooks/<slug>/?share=<token>
  {
    const shareCreateMatch = parsedUrl.pathname.match(/^\/api\/playbooks\/([a-z0-9-]+)\/export\/share$/i);
    if (shareCreateMatch && req.method === 'POST') {
      const slug = shareCreateMatch[1];
      log(`POST /api/playbooks/${slug}/export/share`);
      try {
        const slugDir = path.join(DEPLOY_ROOT, slug);
        if (!fs.existsSync(slugDir)) {
          return sendJSON(res, 404, { error: `Playbook ${slug} not found` });
        }
        pruneExpiredShareTokens();
        const token = generateShareToken();
        const now = new Date();
        const expiresAt = new Date(now.getTime() + SHARE_TTL_DAYS * 86400000);
        const arr = readShareTokens();
        const record = {
          token,
          slug,
          created_at: now.toISOString(),
          expires_at: expiresAt.toISOString(),
          view_count: 0
        };
        arr.push(record);
        writeShareTokens(arr);
        return sendJSON(res, 200, {
          token,
          url: `/playbooks/share/${token}`,
          expires_at: record.expires_at,
          expires_at_human: expiresAt.toUTCString(),
          ttl_days: SHARE_TTL_DAYS
        });
      } catch (err) {
        log(`ERROR share-create: ${err.message}`);
        return sendJSON(res, 500, { error: err.message });
      }
    }
    const shareViewMatch = parsedUrl.pathname.match(/^(?:\/playbooks)?\/share\/([A-Za-z0-9_-]{16,})$/);
    if (shareViewMatch && req.method === 'GET') {
      const token = shareViewMatch[1];
      log(`GET /playbooks/share/${token.slice(0, 8)}...`);
      const record = findShareToken(token);
      if (!record) {
        res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end('<h1>Share link not found</h1><p>This link does not exist.</p>');
      }
      if (Date.parse(record.expires_at) < Date.now()) {
        res.writeHead(410, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end('<h1>Share link expired</h1><p>Ask the sender for a fresh link.</p>');
      }
      incrementShareView(token);
      const target = `/playbooks/${record.slug}/?share=${encodeURIComponent(token)}`;
      res.writeHead(302, { Location: target, 'Cache-Control': 'no-store' });
      return res.end();
    }

    const docxMatch = parsedUrl.pathname.match(/^\/api\/playbooks\/([a-z0-9-]+)\/export\/docx$/i);
    if (docxMatch && req.method === 'POST') {
      const slug = docxMatch[1];
      log(`POST /api/playbooks/${slug}/export/docx`);
      try {
        const slugDir = path.join(DEPLOY_ROOT, slug);
        if (!fs.existsSync(slugDir)) return sendJSON(res, 404, { error: `Playbook ${slug} not found` });
        const buf = await buildPlaybookDocx(slug);
        let company = slug;
        try {
          const s1 = JSON.parse(fs.readFileSync(path.join(DATA_DIR, slug, 'step1-company.json'), 'utf8'));
          if (s1 && s1.company && s1.company.name) company = s1.company.name;
        } catch (_) {}
        const dateStamp = new Date().toISOString().slice(0, 10);
        const safeName = company.replace(/[^A-Za-z0-9 ._-]+/g, '').slice(0, 60).trim() || slug;
        const filename = safeName + ' Playbook ' + dateStamp + '.docx';
        res.writeHead(200, {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'Content-Disposition': 'attachment; filename="' + filename.replace(/"/g, '') + '"',
          'Content-Length': buf.length,
          'Access-Control-Allow-Origin': '*'
        });
        return res.end(buf);
      } catch (err) {
        log(`ERROR docx export: ${err.message}`);
        return sendJSON(res, 500, { error: 'docx_failed', detail: err.message.slice(0, 400) });
      }
    }

    const pdfVisualMatch = parsedUrl.pathname.match(/^\/api\/playbooks\/([a-z0-9-]+)\/export\/pdf-visual$/i);
    if (pdfVisualMatch && req.method === 'POST') {
      const slug = pdfVisualMatch[1];
      log(`POST /api/playbooks/${slug}/export/pdf-visual`);
      try {
        const slugDir = path.join(DEPLOY_ROOT, slug);
        if (!fs.existsSync(slugDir)) return sendJSON(res, 404, { error: `Playbook ${slug} not found` });
        const bust = parsedUrl.searchParams.get('bust') === '1';
        const out = await buildVisualPdf(slug, { bust });
        let company = slug;
        try {
          const s1 = JSON.parse(fs.readFileSync(path.join(DATA_DIR, slug, 'step1-company.json'), 'utf8'));
          if (s1 && s1.company && s1.company.name) company = s1.company.name;
        } catch (_) {}
        const dateStamp = new Date().toISOString().slice(0, 10);
        const safeName = company.replace(/[^A-Za-z0-9 ._-]+/g, '').slice(0, 60).trim() || slug;
        const filename = safeName + ' Playbook ' + dateStamp + ' Visual.pdf';
        res.writeHead(200, {
          'Content-Type': 'application/pdf',
          'Content-Disposition': 'attachment; filename="' + filename.replace(/"/g, '') + '"',
          'Content-Length': out.buffer.length,
          'X-CD-Cache': out.cached ? 'hit-' + Math.round(out.age_ms / 1000) + 's' : 'miss',
          'Access-Control-Allow-Origin': '*'
        });
        return res.end(out.buffer);
      } catch (err) {
        log(`ERROR pdf-visual: ${err.message}`);
        return sendJSON(res, 500, { error: 'pdf_visual_failed', detail: err.message.slice(0, 400) });
      }
    }
  }

  // CLI-1200: list-level running visibility.
  // GET /api/playbooks/_running -> { running: [{ slug, company_name, current_step, current_label, ... }] }
  if (parsedUrl.pathname === '/api/playbooks/_running' && req.method === 'GET') {
    log('GET /api/playbooks/_running');
    try {
      const base = handleRunning();
      const sem = semaphoreSnapshot();
      return sendJSON(res, 200, Object.assign({}, base, sem));
    } catch (err) {
      log(`ERROR: ${err.message}`);
      return sendJSON(res, 500, { error: err.message });
    }
  }

  // CLI-1192: lightweight search-while-filling endpoint.
  // GET /api/playbooks/search?q=<query>&limit=5 -> [{ slug, name, url, last_run, source }]
  if (parsedUrl.pathname === '/api/playbooks/search' && req.method === 'GET') {
    log(`GET /api/playbooks/search?q=${parsedUrl.searchParams.get('q') || ''}`);
    try {
      const q = (parsedUrl.searchParams.get('q') || '').trim().toLowerCase();
      const limit = Math.min(20, Math.max(1, Number(parsedUrl.searchParams.get('limit')) || 5));
      return sendJSON(res, 200, handleSearch(q, limit));
    } catch (err) {
      log(`ERROR: ${err.message}`);
      return sendJSON(res, 500, { error: err.message });
    }
  }

  if (parsedUrl.pathname === '/api/playbooks/_create' && req.method === 'POST') {
    log('POST /api/playbooks/_create');
    return handleCreate(req, res);
  }

  const route = parseRoute(parsedUrl.pathname, req.method);

  if (!route) {
    return sendJSON(res, 404, { error: 'Not found' });
  }

  const { slug, action } = route;
  log(`${req.method} /api/playbooks/${slug}/${action}`);

  try {
    let result;

    switch (action) {
      case 'edit':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleEdit(slug, await parseBody(req));
        break;

      case 'prompt':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handlePrompt(slug, await parseBody(req));
        break;

      case 'upload':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleUpload(slug, req);
        break;

      case 'add-signal':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleAddSignal(slug, await parseBody(req));
        break;

      case 'remove':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleRemove(slug, await parseBody(req));
        break;

      case 'versions':
        if (req.method !== 'GET') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleVersions(slug);
        break;

      case 'rollback':
        if (req.method !== 'POST') return sendJSON(res, 405, { error: 'Method not allowed' });
        result = await handleRollback(slug, await parseBody(req));
        break;

      default:
        return sendJSON(res, 404, { error: `Unknown action: ${action}` });
    }

    sendJSON(res, 200, result);
  } catch (err) {
    log(`ERROR: ${err.message}`);
    sendJSON(res, 500, { error: err.message });
  }
});

server.listen(PORT, () => {
  log(`Playbook Editor API running on port ${PORT}`);
  log(`SKILL_ROOT: ${SKILL_ROOT}`);
  log(`Data dir: ${DATA_DIR}`);
  log(`Deploy root: ${DEPLOY_ROOT}`);
  log(`API key: ${ANTHROPIC_API_KEY ? 'loaded' : 'MISSING'}`);
});
