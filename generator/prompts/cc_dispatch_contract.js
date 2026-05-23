'use strict';

/*
 * CC-dispatch contract : JS twin of cc_dispatch_contract.py.
 *
 * Used by scripts/playbook-editor-proxy.js (the only JS Anthropic call site).
 * Wire-up pattern at the existing callSonnet() site:
 *
 *   const { wrapPromptForCc, parseCcResult } = require('../generator/prompts/cc_dispatch_contract.js');
 *   const wrapped = wrapPromptForCc(userContent, 'proxy_inline_edit');
 *   const raw = await dispatchToCc({ prompt: wrapped, model: 'sonnet', maxTokens: 8192 });
 *   const data = parseCcResult(raw, 'proxy_inline_edit');
 *
 * Schema names and semantics MUST stay in sync with the Python module.
 * If a new prompt site is added, update both files in the same commit.
 */

const MARKER_START = '===CC_RESULT_START===';
const MARKER_END = '===CC_RESULT_END===';

const PROMPT_SCHEMAS = {
  step1_web_search:            { topLevel: 'text',   needsWebSearch: true,  maxTokens: 8192 },
  step1_haiku_extraction:      { topLevel: 'object', needsWebSearch: false, maxTokens: 16000 },
  step2_investor_batch:        { topLevel: 'array',  needsWebSearch: false, maxTokens: 16000 },
  step2b_named_targets:        { topLevel: 'object', needsWebSearch: false, maxTokens: 4000 },
  step2b_fit_notes:            { topLevel: 'array',  needsWebSearch: false, maxTokens: 8000 },
  step3_grants_web_search:     { topLevel: 'text',   needsWebSearch: true,  maxTokens: 8192 },
  step3_grants_eligibility:    { topLevel: 'array',  needsWebSearch: false, maxTokens: 16000 },
  step3_grants_as_bd_search:   { topLevel: 'text',   needsWebSearch: true,  maxTokens: 6000 },
  step3_grants_as_bd_extract:  { topLevel: 'array',  needsWebSearch: false, maxTokens: 4000 },
  step4_market_web_research:   { topLevel: 'text',   needsWebSearch: true,  maxTokens: 12000 },
  step4_market_analysis:       { topLevel: 'object', needsWebSearch: false, maxTokens: 16000 },
  step5_expert_rationale:      { topLevel: 'object', needsWebSearch: false, maxTokens: 8000 },
  step6_synthesis:             { topLevel: 'object', needsWebSearch: false, maxTokens: 20000 },
  proxy_inline_edit:           { topLevel: 'object', needsWebSearch: false, maxTokens: 8192 },
};

class CCResultParseError extends Error {
  constructor(reason, rawExcerpt, schemaName) {
    super(`${reason} (schema=${schemaName})`);
    this.reason = reason;
    this.rawExcerpt = (rawExcerpt || '').slice(0, 2000);
    this.schemaName = schemaName;
  }
}

function wrapPromptForCc(userMsg, schemaName) {
  const schema = PROMPT_SCHEMAS[schemaName];
  if (!schema) throw new Error(`unknown CC prompt schema: ${schemaName}`);
  if (userMsg.includes(MARKER_START) && userMsg.includes(MARKER_END)) {
    return userMsg;
  }
  const top = schema.topLevel;
  let suffix;
  if (top === 'text') {
    suffix =
      '\n\n---\n' +
      'OUTPUT CONTRACT\n' +
      'Respond between the markers below. Plain text is fine; no JSON required.\n' +
      MARKER_START + '\n<your full research dossier here>\n' + MARKER_END + '\n' +
      'Do not emit anything after the closing marker.';
  } else {
    const shape = top === 'object' ? 'JSON object {...}' : 'JSON array [...]';
    suffix =
      '\n\n---\n' +
      'OUTPUT CONTRACT\n' +
      `Respond ONLY between the markers below with a single strict ${shape} matching the schema described above. ` +
      'No markdown fences. No prose outside the markers. No comments inside the JSON.\n' +
      MARKER_START + '\n<' + shape + ' here>\n' + MARKER_END + '\n' +
      `Schema id (for caller's reference, do not echo): ${schemaName}`;
  }
  return userMsg.replace(/\s+$/, '') + suffix;
}

function extractMarkerBlock(text, schemaName) {
  if (typeof text !== 'string') {
    throw new CCResultParseError('not_a_string', String(typeof text), schemaName);
  }
  const start = text.indexOf(MARKER_START);
  if (start < 0) throw new CCResultParseError('missing_start_marker', text, schemaName);
  const afterStart = start + MARKER_START.length;
  const end = text.indexOf(MARKER_END, afterStart);
  if (end < 0) throw new CCResultParseError('missing_end_marker', text.slice(start), schemaName);
  let block = text.slice(afterStart, end).trim();
  block = block.replace(/^```\w*\n?|\n?```$/gm, '').trim();
  return block;
}

function braceBalanced(block, opener, closer) {
  const start = block.indexOf(opener);
  if (start < 0) return null;
  let depth = 0;
  for (let i = start; i < block.length; i++) {
    const ch = block[i];
    if (ch === opener) depth += 1;
    else if (ch === closer) {
      depth -= 1;
      if (depth === 0) return block.slice(start, i + 1);
    }
  }
  return null;
}

function parseCcResult(text, schemaName) {
  const schema = PROMPT_SCHEMAS[schemaName];
  if (!schema) throw new Error(`unknown CC prompt schema: ${schemaName}`);
  const block = extractMarkerBlock(text, schemaName);
  const top = schema.topLevel;
  if (top === 'text') return block;

  let data;
  try { data = JSON.parse(block); }
  catch (_e) {
    const [open, close] = top === 'object' ? ['{', '}'] : ['[', ']'];
    const candidate = braceBalanced(block, open, close);
    if (!candidate) throw new CCResultParseError('malformed_json', block, schemaName);
    try { data = JSON.parse(candidate); }
    catch (e) { throw new CCResultParseError('malformed_json:' + e.message, block, schemaName); }
  }
  if (top === 'object' && (typeof data !== 'object' || Array.isArray(data) || data === null)) {
    throw new CCResultParseError('wrong_top_level:expected_object', block, schemaName);
  }
  if (top === 'array' && !Array.isArray(data)) {
    throw new CCResultParseError('wrong_top_level:expected_array', block, schemaName);
  }
  return data;
}

module.exports = {
  MARKER_START,
  MARKER_END,
  PROMPT_SCHEMAS,
  CCResultParseError,
  wrapPromptForCc,
  parseCcResult,
};

// Self-test: node generator/prompts/cc_dispatch_contract.js
if (require.main === module) {
  let failures = 0;
  function expect(cond, msg) { if (!cond) { console.log('FAIL:', msg); failures += 1; } }

  const wrapped = wrapPromptForCc('EXTRACT FOO.', 'step5_expert_rationale');
  expect(wrapped.includes(MARKER_START) && wrapped.includes(MARKER_END), 'wrap drops markers');

  let r = parseCcResult(`pre\n${MARKER_START}\n{"a":1}\n${MARKER_END}\npost`, 'step5_expert_rationale');
  expect(r.a === 1, 'object parse');

  r = parseCcResult(`${MARKER_START}\n[{"idx":"B0"}]\n${MARKER_END}`, 'step2b_fit_notes');
  expect(Array.isArray(r) && r[0].idx === 'B0', 'array parse');

  r = parseCcResult(`${MARKER_START}\n\`\`\`json\n{"a":1}\n\`\`\`\n${MARKER_END}`, 'step1_haiku_extraction');
  expect(r.a === 1, 'fence-strip');

  r = parseCcResult(`${MARKER_START}\n{"a":1} extra junk\n${MARKER_END}`, 'step1_haiku_extraction');
  expect(r.a === 1, 'trailing-prose fallback');

  r = parseCcResult(`${MARKER_START}\nsome text\n${MARKER_END}`, 'step1_web_search');
  expect(r.includes('some text'), 'text-schema');

  try { parseCcResult('no markers', 'step5_expert_rationale'); failures += 1; console.log('FAIL: missing markers should raise'); }
  catch (e) { expect(e instanceof CCResultParseError, 'missing markers raises CCResultParseError'); }

  try { parseCcResult(`${MARKER_START}\n[1,2]\n${MARKER_END}`, 'step5_expert_rationale'); failures += 1; console.log('FAIL: wrong top level should raise'); }
  catch (e) { expect(e instanceof CCResultParseError, 'wrong top level raises CCResultParseError'); }

  const wrapped2 = wrapPromptForCc(wrapped, 'step5_expert_rationale');
  expect(wrapped2 === wrapped, 'wrap idempotency');

  console.log('selftest:', failures, 'failures');
  process.exit(failures === 0 ? 0 : 1);
}
