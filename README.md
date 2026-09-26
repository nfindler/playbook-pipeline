# playbook-pipeline

Legacy playbook generation and editing service. The GitHub repository is
`nfindler/playbook-pipeline`; the production checkout is named
`/home/openclaw/playbook-skill`. It is separate from `nfindler/playbooks`.

Supabase remains the canonical source of truth and `cd-sot` its HTTP gateway.
This repository's legacy JSON files and rendered outputs are not a new
canonical database.

## Real entrypoint

```sh
node scripts/playbook-editor-proxy.js
```

The HTTP server uses port 4300. It hardcodes its checkout to
`/home/openclaw/playbook-skill`, serves rendered files under
`/var/www/climatedoor/playbooks`, and reads legacy page data from
`/home/openclaw/radar-platform/data/pages`. There is no `index.js` entrypoint
despite the historical package metadata.

The proxy invokes the existing Python sequence in `scripts/step1_*` through
`scripts/step7_assemble.py`, including `step2b_apollo_contacts.py`. Keep those
scripts until their proxy callers have been retired. It also provides editing,
document export, and share handlers. `SKILL.md` and `references/` document the
generation procedure; they are not evidence of a schedule.

## Runtime prerequisites

- Node.js dependencies from `package-lock.json`; Python 3 for pipeline steps.
- Existing production data directories and the deployment paths listed above.
- Authentication configured for the proxy. It reads `AUTH_USER`, `AUTH_PASS`,
  and `CD_TRUST_COOKIE_AUTH`; cookie verification is in
  `scripts/cd-session-verify.js`. Preserve the current access gates.
- `ANTHROPIC_API_KEY` for model operations; legacy fallback reads the Radar
  checkout's private environment. Pipeline subprocesses also receive
  `APOLLO_API_KEY` when present.
- Puppeteer and a compatible browser for PDF rendering. Test installation can
  skip install scripts because the unit suite does not render PDFs.

Starting the service is not a safe validation command: production paths and paid
model or integration operations are present. The repository is not self-contained
for a new deployment and must not be presented as such.

## Validation

With Node.js 20 or later and Python 3:

```sh
npm ci --ignore-scripts
npm test
```

The existing command runs Jest session verification tests and the Python step-7
escaping regression cases. It does not execute the generation pipeline, contact
production services, or validate PDF rendering.

## Retirement status

Retained after the 2026-09-26 UTC production inspection:

- Portal PM2 listed `playbook-editor` online with `playbook-editor-proxy.js`.
- `/proc/1858885/cwd` resolved to `/home/openclaw/playbook-skill`.
- That checkout's Git origin is `nfindler/playbook-pipeline.git`.
- Current `/etc/caddy/Caddyfile` proxies `/api/playbooks/*` and the dynamic
  fallback under `/playbooks/*` to `127.0.0.1:4300`.

These are live-caller proofs, so the archive condition is not met. No operational
scripts, backups, generation data, deployed pages, skills, cron entries, or
database rows were deleted. This documentation changes no process or schedule.
