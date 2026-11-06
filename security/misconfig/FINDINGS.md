# Misconfiguration & vulnerable dependencies — findings

Section 2.7, Intermediate. Scope: the FastAPI backend and the built React
front end. Raw tool output for every run below is committed under
`security/misconfig/reports/{before,after}/`; nothing here is estimated.

## How to reproduce

```bash
# Backend (from the repository root)
../.venv/bin/python -m pip_audit -r backend/requirements.txt

# Frontend (from frontend/)
npm audit
npm audit --omit=dev

# Headers, both states (from the repository root)
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 --no-server-header &
../security/misconfig/demo_headers.sh
SECURITY_DEFENCES=off ../.venv/bin/uvicorn app.main:app --port 8000 --no-server-header &
../security/misconfig/demo_headers.sh

# OWASP ZAP baseline (needs Docker running)
docker run --rm -v "$(pwd)/security/misconfig/reports:/zap/wrk:rw" \
  -t zaproxy/zap-stable zap-baseline.py \
  -t http://host.docker.internal:8000/openapi.json -f openapi \
  -r after/zap-api.html -J after/zap-api.json
# Front end: build + `vite preview`, then point ZAP at http://host.docker.internal:4173
# with FRONTEND_ORIGIN=http://localhost:4173 on the backend so the UI can
# actually call the API during the crawl (see note below).
```

**Note on the front-end scan origin:** `vite preview` serves the built app
on port 4173, not 5173. The backend's CORS allow-list is intentionally one
exact origin (`FRONTEND_ORIGIN`, default `http://localhost:5173`), so a
request from the preview build is rejected by CORS, not by anything ZAP is
testing. Rather than widen CORS, `FRONTEND_ORIGIN=http://localhost:4173` is
set for the duration of the scan only, and the README documents this as a
scan-time override, not a permanent relaxation.

## Dependency findings

| Tool | Package | Severity | Affects this app? | Action | Before → After |
|---|---|---|---|---|---|
| `pip-audit` | (none) | — | — | — | Clean both runs: `reports/{before,after}/pip-audit.txt` |
| `npm audit` | axios 1.19.0 | High | Yes — the only HTTP client the front end uses, talking to an origin the user doesn't control if the app is ever deployed behind a reverse proxy. CVEs include ReDoS and prototype-pollution-based request tampering. | **Fixed** — upgraded to 1.21.0 (`npm install --save-exact axios@1.21.0`) | 12 advisories → 0 |
| `npm audit` | follow-redirects 1.16.0–1.16.1 (transitive, via axios) | High | Indirect — axios depends on it for the Node adapter, unused in the browser build but still resolved and audited. | **Fixed** — resolved to 1.16.2 as part of the axios upgrade + `npm audit fix` | 3 advisories → 0 |
| `npm audit` | source-map-js 1.0.0–1.2.1 (transitive, via vite→postcss, dev only) | High | Marginal — a build-time-only dependency; the ReDoS triggers on parsing an attacker-controlled source map, which this project never does with untrusted input. Still fixed since the upgrade was free. | **Fixed** — resolved to 1.2.2 as part of the vite upgrade | 1 advisory → 0 |
| `npm audit` | vite 8.2.0–8.2.2 (dev only) | High | Marginal for most advisories (the `launch-editor` ones need the dev server's "open in editor" feature, never exposed outside localhost); the cross-origin-script-execution and `server.fs` advisories are relevant to any exposed dev server. Not shipped in the production build regardless. | **Fixed** — upgraded to 8.3.6 (`npm install --save-exact vite@8.3.6`) | 6 advisories → 0 |

`npm audit --omit=dev` before: 2 (axios, follow-redirects); after: 0.
Full `npm audit` before: 4 packages / 24 advisories; after: 0 (`reports/{before,after}/npm-audit.txt`).

Upgrading did not require any code change: `npm run build`, `npm run
lint` and the full Playwright e2e suite all still pass (see Part B).

## Misconfiguration findings

| # | Finding | Severity | Action | Fix |
|---|---|---|---|---|
| 1 | No `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Content-Security-Policy` or `Permissions-Policy` on any API response. | Medium | **Fixed** | `backend/app/security/headers.py` + `SecurityHeadersMiddleware`, applied to every response including 413/422/500 (see tests in `backend/tests/test_security_headers.py`). |
| 2 | `/score` responses had no `Cache-Control`, so a shared proxy or the browser's back/forward cache could retain a previously-scored passage. | Low | **Fixed** | `Cache-Control: no-store` added specifically on `/api/v1/score`. |
| 3 | Uvicorn's default `Server: uvicorn` response header discloses the server software, aiding reconnaissance. | Low | **Fixed** | Documented run command uses `--no-server-header`; see README. |
| 4 | `/redoc` was enabled by default, duplicating `/docs` against the same OpenAPI document, and would have needed a third external CSP origin (Google Fonts) to render under the relaxed docs policy. | Low | **Fixed** | Disabled (`redoc_url=None` in `app.main`); `/docs` remains the one interactive API reference. |
| 5 | Front end (Vite dev server and `vite preview`) served no security headers at all. | Medium | **Fixed** | `vite.config.ts` `server.headers` / `preview.headers`, mirroring the backend's header set; CSP is intentionally looser in dev (documented inline) for Vite's own HMR tooling, strict in the production build. |
| 6 | OWASP ZAP baseline scan | — | **Pending** | Needs Docker; not yet run at the time this file was last updated. Results will be appended to `reports/{before,after}/zap-*` and this table once available. |

## Cost

- **A strict `Content-Security-Policy` constrains future features.** Adding
  any new third-party script, font, analytics tag, or embedded widget to
  either the API docs page or the front end requires explicitly widening
  the relevant `*-src` directive — the policy fails closed, by design, so
  a forgotten directive breaks the feature loudly (console error) rather
  than silently leaving a hole.
- **Dependency upgrades carry (low, here) breaking-change risk.** axios
  1.19.0 → 1.21.0 and vite 8.2.2 → 8.3.6 are both within their current
  major version, and the full build/lint/e2e suite was re-run after each
  to confirm nothing broke — but a future advisory may not be fixable by a
  same-major bump, and will need the same verification repeated.
- **`npm audit`'s dev-only findings (vite, source-map-js) are a weaker
  signal than the runtime ones.** They were fixed here because the fix was
  free, not because this app is meaningfully exposed to them in
  production — the distinction matters when deciding whether a future
  dev-only advisory is worth an urgent upgrade.
- **`--no-server-header` and disabling `/redoc` are pure information-
  hygiene fixes** with no functional cost; worth doing regardless of
  threat model.
