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

# OWASP ZAP (needs Docker running), from the repository root
# API: the OpenAPI document drives a targeted scan of every documented
# endpoint, rather than a generic crawl of a JSON-only service a spider
# cannot meaningfully click through.
docker run --rm -v "$(pwd)/security/misconfig/reports:/zap/wrk:rw" \
  -t zaproxy/zap-stable zap-api-scan.py \
  -t http://host.docker.internal:8000/openapi.json -f openapi \
  -r after/zap-api.html -J after/zap-api.json

# Front end: build + `vite preview` first (port 4173). vite preview rejects
# requests whose Host header it doesn't recognise, which is exactly what
# ZAP's container sends (`host.docker.internal`), so a ZAP Replacer rule
# rewrites the Host header back to `localhost:4173` before each request
# reaches the server, passed via -z (inline ZAP config overrides).
# FRONTEND_ORIGIN=http://localhost:4173 on the backend lets the served app
# actually call the API during the crawl -- see note below.
docker run --rm -v "$(pwd)/security/misconfig/reports:/zap/wrk:rw" \
  -t zaproxy/zap-stable zap-baseline.py \
  -t http://host.docker.internal:4173 \
  -z "-config replacer.full_list(0).description=hostheader \
      -config replacer.full_list(0).enabled=true \
      -config replacer.full_list(0).matchtype=REQ_HEADER \
      -config replacer.full_list(0).matchstr=Host \
      -config replacer.full_list(0).regex=false \
      -config replacer.full_list(0).replacement=localhost:4173" \
  -r after/zap-frontend.html -J after/zap-frontend.json
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

## Misconfiguration findings — headers, before ZAP ran

Found by manual review (`curl -i`) before any scanner was run, and fixed
before the first ZAP scan in `reports/before/`:

| # | Finding | Severity | Action | Fix |
|---|---|---|---|---|
| 1 | No `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Content-Security-Policy` or `Permissions-Policy` on any API response. | Medium | **Fixed** | `backend/app/security/headers.py` + `SecurityHeadersMiddleware`, applied to every response including 413/422/500 (see tests in `backend/tests/test_security_headers.py`). |
| 2 | `/score` responses had no `Cache-Control`, so a shared proxy or the browser's back/forward cache could retain a previously-scored passage. | Low | **Fixed** | `Cache-Control: no-store` added specifically on `/api/v1/score`. |
| 3 | Uvicorn's default `Server: uvicorn` response header discloses the server software, aiding reconnaissance. | Low | **Fixed** | Documented run command uses `--no-server-header`; see README. |
| 4 | `/redoc` was enabled by default, duplicating `/docs` against the same OpenAPI document, and would have needed a third external CSP origin (Google Fonts) to render under the relaxed docs policy. | Low | **Fixed** | Disabled (`redoc_url=None` in `app.main`); `/docs` remains the one interactive API reference. |
| 5 | Front end (Vite dev server and `vite preview`) served no security headers at all. | Medium | **Fixed** | `vite.config.ts` `server.headers` / `preview.headers`, mirroring the backend's header set; CSP is intentionally looser in dev (documented inline) for Vite's own HMR tooling, strict in the production build. |

## ZAP findings, per alert

Every row is built directly from `reports/{before,after}/zap-{api,frontend}.json`
(`alertid`/`pluginid`, `name`, `riskdesc`, instance URLs). `reports/before/`
reflects the headers fixed above (round 1); `reports/after/` reflects those
plus the cheap fixes below (round 2: `Cross-Origin-Resource-Policy`,
`base-uri`/`form-action`, and — front end only — `Cross-Origin-Opener-Policy`).
**The committed `after/` JSON/HTML predate round 2** (it was run against
round-1 headers only); the rows marked *fixed, pending re-scan* below are
code changes made after that scan, not yet confirmed by a fresh ZAP run.
This file will be updated once the AFTER scans are re-run against round 2.

### API (`zap-api-scan.py` against `/openapi.json`)

| Plugin | Alert | Risk | URLs (sample) | Before | After (round 1) | Action |
|---|---|---|---|---|---|---|
| 90004 | Cross-Origin-Resource-Policy Header Missing or Invalid | Low (Medium) | `/api/v1/health`, `/api/v1/model-info`, `/openapi.json` | 3 instances | 3 instances (unchanged by round 1) | **Fixed, pending re-scan** — `Cross-Origin-Resource-Policy: same-site` added in round 2 (not `same-origin`: the front end calls this API cross-port on the same host, which is same-site but not same-origin) |
| 10021 | X-Content-Type-Options Header Missing | Low (Medium) | `/api/v1/health`, `/api/v1/model-info`, `/openapi.json` | 3 instances | **0** | **Fixed** (round 1) |
| 100000 | A Client Error response code was returned by the server | Informational (High) | `/`, `/{spider-guessed-path}` | 19 instances | 19 instances | **Accepted, no action** — these are the spider's own 404 probes against paths that do not exist; a 404 (not a 500 or a stack trace) is the correct, intended response and is exactly what `backend/tests/test_error_handling.py::test_404_uses_error_envelope` checks |
| 10049 | Non-Storable Content | Informational (Medium) | `/api/v1/score` | 1 instance | 1 instance | **Accepted, no action** — this is `Cache-Control: no-store` on `/score` (finding 2 above) being correctly observed, not a gap |
| 10049 | Storable and Cacheable Content | Informational (Medium) | `/api/v1/health`, `/api/v1/model-info`, `/openapi.json` | 3 instances | 3 instances | **Accepted, no action** — none of these three responses are sensitive or user-specific; being cacheable by an intermediary is harmless and, for `/openapi.json` in particular, desirable |

### Front end (`zap-baseline.py` against the `vite preview` build)

| Plugin | Alert | Risk | Before | After (round 1) | Action |
|---|---|---|---|---|---|
| 10038 | Content Security Policy (CSP) Header Not Set | Medium (High) | 3 instances | **0** | **Fixed** (round 1) |
| 10020 | Missing Anti-clickjacking Header | Medium (Medium) | 3 instances | **0** | **Fixed** (round 1) — `X-Frame-Options: DENY` |
| 10063 | Permissions Policy Header Not Set | Low (Medium) | 4 instances | **0** | **Fixed** (round 1) |
| 10021 | X-Content-Type-Options Header Missing | Low (Medium) | 5 instances | **0** | **Fixed** (round 1) |
| 90004 | Cross-Origin-Resource-Policy Header Missing or Invalid | Low (Medium) | 4 instances | 3 instances | **Fixed, pending re-scan** — `same-site`, round 2 |
| 90004 | Cross-Origin-Opener-Policy Header Missing or Invalid | Low (Medium) | 3 instances | 3 instances | **Fixed, pending re-scan** — `same-origin`, round 2 |
| 90004 | Cross-Origin-Embedder-Policy Header Missing or Invalid | Low (Medium) | 3 instances | 3 instances | **Justified, accepted risk** — see below |
| 10055 | CSP: Failure to Define Directive with No Fallback | Medium (High) | *(CSP did not exist yet)* | 2 instances (new, caused by round 1's own CSP) | **Fixed, pending re-scan** — `base-uri 'self'; form-action 'self'` added, round 2 |
| 10055 | CSP: style-src unsafe-inline | Medium (High) | *(CSP did not exist yet)* | 3 instances (new, caused by round 1's own CSP) | **Justified, accepted risk** — see below |
| 10096 | Timestamp Disclosure - Unix | Low (Low) | 1 instance | 1 instance | **False positive, justified** — see below |
| 10027 | Information Disclosure - Suspicious Comments | Informational (Medium) | 1 instance | 1 instance | **False positive, justified** — see below |
| 10109 | Modern Web Application | Informational (Medium) | 3 instances | 3 instances | **Accepted, no action** — ZAP's own description says so: "This is an informational alert and so no changes are required" |
| 10049 | Storable but Non-Cacheable Content | Informational (Medium) | 5 instances | 5 instances | **Accepted, no action** — `vite preview`'s own default `Cache-Control: no-cache` on its static files; not something this app's code sets or needs to change |

**Summary counts** (alert rows, not instances): API 5 → 4 (round 1) → 3
expected after round 2's re-scan. Front end 11 → 9 (round 1, with 2 new
CSP sub-findings caused by introducing the CSP in the first place) → 6
expected after round 2 (3 `90004` rows fixed, 1 `10055` row fixed, `10055`
style-src and `90004` COEP remain, justified below, plus the 3
always-accepted informational rows).

### Justifications for findings left open

- **`style-src 'unsafe-inline'`.** MUI's emotion engine injects `<style>`
  tags at runtime to implement the `sx` prop and styled-components API,
  with no CSP nonce or hash support in its default configuration (emotion
  does support a nonce via `<CacheProvider>`, but wiring that through
  requires generating and serving a fresh per-request nonce from the
  server, which this static single-page app has no server-side rendering
  step to do). Without `'unsafe-inline'` on `style-src`, the app does not
  render at all. The risk this normally guards against — an attacker
  injecting an arbitrary `<style>` tag — is narrow for a pure CSS
  injection (no script execution), and `script-src` (where the real risk
  of injected code execution lives) stays strict (`'self'` only in the
  production build).
- **Cross-Origin-Embedder-Policy (COEP).** Not set, on either the API or
  the front end. COEP's purpose is to let a page opt in to powerful,
  cross-origin-isolated APIs (`SharedArrayBuffer`, high-resolution
  timers) by proving every cross-origin resource it loads has
  explicitly granted permission via CORP or CORS. This app uses none of
  those APIs. Setting `require-corp` would require auditing every
  cross-origin resource the front end loads (currently: the Swagger UI
  CDN scripts/styles on `/docs`, and `/model-info`/`/score` calls to the
  API) and could silently break any of them if a CORP header were ever
  missing upstream — a real cost for a protection this app gets no
  benefit from. Revisit if cross-origin isolation is ever actually needed.
- **Timestamp Disclosure - Unix** (evidence: `1540483477`, found in the
  minified JS bundle). This is not a timestamp. `1540483477` (`0x5bd1e995`)
  is the fixed multiplier constant of the MurmurHash2 algorithm, used by
  `@emotion/hash` (a dependency of MUI's styling engine) to generate CSS
  class names from style content — confirmed by locating the exact match
  in `frontend/dist/assets/*.js` (`...n=(n&65535)*1540483477+((n>>>16)*59797<<16)...`,
  the textbook MurmurHash2 inner loop). ZAP's Unix-timestamp detector is a
  generic "is this a plausible 10-digit number" pattern match and has no
  way to tell a hash constant from an epoch value. No fix needed or
  possible without replacing a correctly-functioning third-party library.
- **Information Disclosure - Suspicious Comments** (evidence excerpt:
  `function Db(e){let t=V.useContext(...` — a minified react-router
  internal, not a comment at all). Grepping the full built bundle
  (`grep -oE '/\*[^*]{0,80}' frontend/dist/assets/*.js`) for every
  comment-opening sequence finds 16 matches, all of them build-tool
  artifacts preserved by the minifier — e.g. `/* @noflip */`, a
  standard directive used by `stylis` (MUI/emotion's CSS pre-processor)
  to mark a rule that should not be mirrored for right-to-left layouts.
  None of the 16 is a developer comment, a TODO, or anything that
  describes this application's own implementation; they all originate
  inside third-party library code bundled as-is. No fix applicable.

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
- **`Cross-Origin-Resource-Policy: same-site` (not `same-origin`) was a
  deliberate choice, not the stricter default ZAP's own solution text
  suggests.** This app's front end and backend genuinely run on different
  origins by the browser's definition (same host, different port), so
  `same-origin` would have blocked the app's own API calls; `same-site`
  is the tightest value that does not do that. Any future change that
  moves the front end to a genuinely different site (not just a different
  port) needs this revisited.
- **Running ZAP against the built front end, not the dev server, means the
  dev-only CSP allowances (`'unsafe-eval'`, the extra `'unsafe-inline'` on
  `script-src`, the HMR websocket) were never scanned.** That is
  intentional — they do not ship to production — but it also means ZAP
  never got a chance to flag them, so they are not "passed", only
  out of scope for this tool.
