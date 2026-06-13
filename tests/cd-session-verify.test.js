'use strict';

// CLI-2790: the proxy's cd_session cookie path verifies the VALUE via
// Supabase, fail-closed everywhere. These tests drive the module through its
// DI seams (fetchImpl / nowImpl / env) -- no network, no real clock.

const { verifyCdSession, _internal } = require('../scripts/cd-session-verify');

const ENV_OK = { SUPABASE_URL: 'https://sb.example.com', SUPABASE_ANON_KEY: 'anon-key' };

function okResponse(body) {
  return { ok: true, json: async () => body };
}
function unauthorizedResponse() {
  return { ok: false, status: 401, json: async () => ({ msg: 'invalid token' }) };
}

beforeEach(() => _internal._clearForTests());

describe('extractCdSession', () => {
  test('pulls the cd_session value out of a multi-cookie header', () => {
    expect(_internal.extractCdSession('a=1; cd_session=tok-123; b=2')).toBe('tok-123');
  });
  test('decodes URL-encoded values', () => {
    expect(_internal.extractCdSession('cd_session=ey%2Fabc%3D%3D')).toBe('ey/abc==');
  });
  test('no cd_session entry yields empty', () => {
    expect(_internal.extractCdSession('other=1; cd_sessionx=evil')).toBe('');
    expect(_internal.extractCdSession('')).toBe('');
    expect(_internal.extractCdSession(null)).toBe('');
  });
});

describe('verifyCdSession fail-closed paths', () => {
  test('no cookie -> false without touching the network', async () => {
    const fetchImpl = jest.fn();
    await expect(verifyCdSession('', { fetchImpl, env: ENV_OK })).resolves.toBe(false);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test('missing Supabase config -> false without touching the network', async () => {
    const fetchImpl = jest.fn();
    const noConfig = { env: {}, envFile: '/nonexistent/.env', fetchImpl };
    await expect(verifyCdSession('cd_session=anything', noConfig)).resolves.toBe(false);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test('Supabase 401 (garbage token) -> false, and the verdict is cached', async () => {
    const fetchImpl = jest.fn(async () => unauthorizedResponse());
    const deps = { fetchImpl, env: ENV_OK, nowImpl: () => 1_000 };
    await expect(verifyCdSession('cd_session=garbage', deps)).resolves.toBe(false);
    await expect(verifyCdSession('cd_session=garbage', deps)).resolves.toBe(false);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test('network error -> false and NOT cached (next request retries)', async () => {
    const fetchImpl = jest.fn(async () => { throw new Error('ETIMEDOUT'); });
    const deps = { fetchImpl, env: ENV_OK, nowImpl: () => 1_000 };
    await expect(verifyCdSession('cd_session=tok', deps)).resolves.toBe(false);
    await expect(verifyCdSession('cd_session=tok', deps)).resolves.toBe(false);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  test('200 with a body lacking id/email -> false (no half-auth)', async () => {
    const fetchImpl = jest.fn(async () => okResponse({ role: 'anon' }));
    await expect(verifyCdSession('cd_session=tok', { fetchImpl, env: ENV_OK })).resolves.toBe(false);
  });
});

describe('verifyCdSession happy path + cache', () => {
  test('a Supabase-confirmed token -> true, cached inside the TTL', async () => {
    const fetchImpl = jest.fn(async () => okResponse({ id: 'user-1', email: 'a@b.c' }));
    let now = 10_000;
    const deps = { fetchImpl, env: ENV_OK, nowImpl: () => now };
    await expect(verifyCdSession('cd_session=live-token', deps)).resolves.toBe(true);
    now += _internal.CACHE_TTL_MS - 1;
    await expect(verifyCdSession('cd_session=live-token', deps)).resolves.toBe(true);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  test('the verdict expires after the TTL and re-verifies', async () => {
    const fetchImpl = jest.fn(async () => okResponse({ id: 'user-1' }));
    let now = 10_000;
    const deps = { fetchImpl, env: ENV_OK, nowImpl: () => now };
    await verifyCdSession('cd_session=live-token', deps);
    now += _internal.CACHE_TTL_MS + 1;
    await verifyCdSession('cd_session=live-token', deps);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  test('the Bearer header carries the decoded cookie value', async () => {
    const fetchImpl = jest.fn(async () => okResponse({ id: 'u' }));
    await verifyCdSession('cd_session=ey%2Fabc', { fetchImpl, env: ENV_OK });
    const [url, opts] = fetchImpl.mock.calls[0];
    expect(url).toBe('https://sb.example.com/auth/v1/user');
    expect(opts.headers.authorization).toBe('Bearer ey/abc');
    expect(opts.headers.apikey).toBe('anon-key');
  });
});

describe('supabaseConfig fallback', () => {
  test('env wins; the platform .env is only a fallback', () => {
    const readEnvKeyImpl = jest.fn(() => 'from-file');
    const cfg = _internal.supabaseConfig({ env: ENV_OK, readEnvKeyImpl });
    expect(cfg).toEqual({ url: 'https://sb.example.com', anonKey: 'anon-key' });
    expect(readEnvKeyImpl).not.toHaveBeenCalled();
  });

  test('missing env falls back to the platform .env file', () => {
    const readEnvKeyImpl = jest.fn((_f, key) => (key === 'SUPABASE_URL' ? 'https://file.example.com/' : 'file-anon'));
    const cfg = _internal.supabaseConfig({ env: {}, readEnvKeyImpl });
    expect(cfg).toEqual({ url: 'https://file.example.com', anonKey: 'file-anon' });
  });
});
