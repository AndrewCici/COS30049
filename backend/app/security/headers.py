"""Security response headers, applied to every response including errors.

Raw ASGI (not BaseHTTPMiddleware), for the same reason as the body-size
middleware: it must be able to wrap responses that never reach a route
handler at all -- notably the body-size middleware's own 413, generated
before routing even starts. It is also the outermost user middleware (see
app.main's middleware registration comment), so no later handler can omit
a header by forgetting to add it. The one response this middleware cannot
reach is a truly unhandled exception's 500: Starlette's ServerErrorMiddleware
sends that response from outside every user middleware, so
app.main.unhandled_exception_handler adds the same headers by hand, the
same way it already has to for the CORS header.

Gated by SECURITY_DEFENCES (off disables it, same as the DoS defences) so
the misconfiguration demo can show "before" behaviour.
"""
from .. import config

# FastAPI's default /docs (Swagger UI) page loads its JS/CSS from a CDN
# and runs an inline bootstrap <script> with no nonce; the API's own JSON
# endpoints execute nothing and need no such allowance. (/redoc is
# disabled in app.main -- it would need a third external origin for
# fonts, for a page that only duplicates /docs.) See
# security/misconfig/FINDINGS.md for the finding this resolves.
DOCS_PATHS = frozenset({"/docs", "/openapi.json", "/docs/oauth2-redirect"})

# base-uri and form-action have no fallback to default-src (unlike most
# directives), so an otherwise-strict policy that omits them still leaves
# <base> injection and form-hijacking open; ZAP's "Failure to Define
# Directive with No Fallback" flags exactly this gap. Neither API response
# contains a <base> tag or an HTML <form>, so 'self' is simply the
# tightest value that is still correct.
_NO_FALLBACK_DIRECTIVES = "base-uri 'self'; form-action 'self'"

API_CSP = f"default-src 'none'; {_NO_FALLBACK_DIRECTIVES}; frame-ancestors 'none'"
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    f"{_NO_FALLBACK_DIRECTIVES}; "
    "frame-ancestors 'none'"
)

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    # 'same-site' (not the stricter 'same-origin'): the front end calls this
    # API from a different port on the same host (e.g. localhost:5173 ->
    # localhost:8000), which is same-site but not same-origin, and that
    # cross-port call must keep working.
    "Cross-Origin-Resource-Policy": "same-site",
}


def headers_for_path(path: str) -> dict[str, str]:
    headers = dict(BASE_HEADERS)
    headers["Content-Security-Policy"] = DOCS_CSP if path in DOCS_PATHS else API_CSP
    # /score processes pasted text that may be sensitive (e.g. unpublished
    # student work); nothing about a scoring result should be cached by an
    # intermediary or the browser's back/forward cache.
    if path == "/api/v1/score":
        headers["Cache-Control"] = "no-store"
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not config.security_defences_enabled():
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                for name, value in headers_for_path(path).items():
                    existing.append((name.lower().encode(), value.encode()))
                message = {**message, "headers": existing}
            await send(message)

        await self.app(scope, receive, send_with_headers)
