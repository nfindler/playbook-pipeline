'use strict';

/*
 * scripts/cd-session-verify.js -- CLI-2790: REAL verification for the proxy's
 * CD_TRUST_COOKIE_AUTH cookie path.
 *
 * The old gate accepted cookie NAME presence (any browser can self-set a
 * cd_session cookie with any value) as a full basic-auth bypass: the same
 * presence-only class fixed on the platform REST (CLI-1881) and WebSocket
 * (CLI-2772) surfaces. This module is the proxy's port of the platform's
 * verifySessionCookie (playbook-platform lib/auth-middleware.js): the cookie
 * value IS a Supabase access_token, so a /auth/v1/user round-trip verifies
 * signature + exp + revocation server-side.
 *
 * Fail direction: CLOSED everywhere (missing config, network error, non-200).
 * Unlike the platform REST path (fail-open so a Supabase outage cannot lock
 * the dashboard), the proxy always has basic auth as the fallback prompt: a
 * rejected cookie only means the browser asks for credentials, so the safe
 * direction costs nothing (the CLI-2772 posture).
 *
 * Config: SUPABASE_URL / SUPABASE_ANON_KEY from the proxy env when present,
 * else hand-parsed from the platform deploy .env (the repo's cross-service
 * env pattern, same as the step scripts' radar-platform/.env loads). Missing
 * config never bypasses: it disables the cookie path and logs once.
 */

const fs = require('fs');

const CACHE_TTL_MS = 60_000;
const CACHE_MAX = 500;
const VERIFY_TIMEOUT_MS = 2500;
const PLATFORM_ENV_FILE = '/home/openclaw/playbook-platform/.env';

function readEnvKey(file, key) {
  try {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      const t = line.trim();
      if (!t || t.startsWith('#')) continue;
      const i = t.indexOf('=');
      if (i < 1) continue;
      if (t.slice(0, i).trim() === key) return t.slice(i + 1).trim();
    }
  } catch (_e) { /* unreadable file = no config = fail closed */ }
  return '';
}

function supabaseConfig(deps) {
  const d = deps || {};
  const env = d.env || process.env;
  const envFile = d.envFile || PLATFORM_ENV_FILE;
  const read = d.readEnvKeyImpl || readEnvKey;
  const url = (env.SUPABASE_URL || read(envFile, 'SUPABASE_URL')).replace(/\/$/, '');
  const anonKey = env.SUPABASE_ANON_KEY || read(envFile, 'SUPABASE_ANON_KEY');
  return { url, anonKey };
}

function extractCdSession(cookieHeader) {
  const m = /(?:^|;\s*)cd_session=([^;]+)/.exec(String(cookieHeader || ''));
  if (!m) return '';
  try {
    return decodeURIComponent(m[1]).trim();
  } catch (_e) {
    return m[1].trim();
  }
}

// token -> { ok, expiresAt }. Same shape as the platform's verdict cache: a
// 60s TTL bounds both the Supabase QPS and the revoked-token window.
const _verdictCache = new Map();

function _cacheGet(token, now) {
  const v = _verdictCache.get(token);
  if (!v) return undefined;
  if (v.expiresAt <= now) {
    _verdictCache.delete(token);
    return undefined;
  }
  return v.ok;
}

function _cacheSet(token, ok, now) {
  _verdictCache.set(token, { ok, expiresAt: now + CACHE_TTL_MS });
  if (_verdictCache.size > CACHE_MAX) {
    for (const [k, v] of _verdictCache) {
      if (v.expiresAt <= now) _verdictCache.delete(k);
    }
    // Still oversized after dropping expired entries: drop oldest-inserted.
    while (_verdictCache.size > CACHE_MAX) {
      _verdictCache.delete(_verdictCache.keys().next().value);
    }
  }
}

let _warnedNoConfig = false;

/*
 * verifyCdSession(cookieHeader, deps?) -> Promise<boolean>
 * deps: { fetchImpl?, nowImpl?, env?, envFile?, readEnvKeyImpl? } (test seams)
 * true ONLY when Supabase confirms the cookie value as a live access_token.
 */
async function verifyCdSession(cookieHeader, deps) {
  const d = deps || {};
  const token = extractCdSession(cookieHeader);
  if (!token) return false;

  const { url, anonKey } = supabaseConfig(d);
  if (!url || !anonKey) {
    if (!_warnedNoConfig) {
      _warnedNoConfig = true;
      console.warn('[cd-session-verify] SUPABASE_URL/SUPABASE_ANON_KEY unavailable; cookie auth disabled (fail-closed), basic auth still works');
    }
    return false;
  }

  const now = (d.nowImpl || Date.now)();
  const cached = _cacheGet(token, now);
  if (cached !== undefined) return cached;

  const fetchFn = d.fetchImpl || fetch;
  let res;
  try {
    res = await fetchFn(url + '/auth/v1/user', {
      method: 'GET',
      headers: { apikey: anonKey, authorization: 'Bearer ' + token },
      signal: AbortSignal.timeout(VERIFY_TIMEOUT_MS),
    });
  } catch (err) {
    // Network-level failure: fail CLOSED (the browser falls back to the basic
    // auth prompt). Deliberately NOT cached so the next request re-tries
    // Supabase the moment it recovers (the platform middleware's posture).
    console.warn('[cd-session-verify] network error (fail-closed):', err && err.message ? err.message : err);
    return false;
  }

  let ok = false;
  if (res && res.ok) {
    try {
      const body = await res.json();
      ok = !!(body && (body.id || body.email));
    } catch (_e) {
      ok = false;
    }
  }
  _cacheSet(token, ok, now);
  return ok;
}

module.exports = { verifyCdSession };
module.exports._internal = {
  CACHE_TTL_MS, CACHE_MAX, VERIFY_TIMEOUT_MS, PLATFORM_ENV_FILE,
  readEnvKey, supabaseConfig, extractCdSession,
  _verdictCache,
  _clearForTests() { _verdictCache.clear(); _warnedNoConfig = false; },
};
