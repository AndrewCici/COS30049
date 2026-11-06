#!/usr/bin/env bash
# Demonstrates the security-headers defence with SECURITY_DEFENCES off vs
# on, against a live backend. Prints response headers (not bodies) for:
#   - GET  /api/v1/health            -> 200
#   - POST /api/v1/score (422)       -> malformed input
#   - POST /api/v1/score (413)       -> oversized body
#
# Usage:
#   cd backend && ../.venv/bin/uvicorn app.main:app --port 8000 --no-server-header &
#   ../security/misconfig/demo_headers.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BIG_BODY=$(python3 -c "import json; print(json.dumps({'text': 'word '*20000}))")

section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

show() {
  local label="$1"; shift
  printf '\n-- %s --\n' "$label"
  curl -s -D - -o /dev/null "$@" | tr -d '\r'
}

run_all() {
  show "GET /api/v1/health (200)" "$BASE_URL/api/v1/health"
  show "POST /api/v1/score (422, text too short)" \
    -X POST "$BASE_URL/api/v1/score" -H "Content-Type: application/json" -d '{"text":"short"}'
  show "POST /api/v1/score (413, oversized body)" \
    -X POST "$BASE_URL/api/v1/score" -H "Content-Type: application/json" -d "$BIG_BODY"
}

section "Headers are controlled by the SECURITY_DEFENCES env var on the running server -- this script only sends requests and prints what comes back."

section "=== Current server (whatever SECURITY_DEFENCES it was started with) ==="
run_all

cat <<'EOF'

To compare both states directly, run this script twice against two
separately started servers:

    SECURITY_DEFENCES=off  uvicorn app.main:app --port 8000 --no-server-header   # then run this script
    SECURITY_DEFENCES=on   uvicorn app.main:app --port 8000 --no-server-header   # (the default) then run this script again

With it off: no X-Content-Type-Options / Referrer-Policy / X-Frame-Options /
Content-Security-Policy / Permissions-Policy / Cache-Control headers.
With it on (default): all present, as shown above.
EOF
