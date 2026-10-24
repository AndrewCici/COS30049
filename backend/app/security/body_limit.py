"""Request body size limit, enforced as a raw ASGI middleware (not
`BaseHTTPMiddleware`) so it can refuse to keep reading the stream the moment
the limit is crossed, instead of buffering an unbounded body into memory
first and rejecting only after the fact.

Two cases are covered: a `Content-Length` header that already says the body
is too large (rejected without reading anything), and a body that turns out
to be too large as it streams in — whether because `Content-Length` was
missing, wrong, or the request used chunked transfer encoding. In the
second case we read chunk by chunk, stop and reject the instant the running
total exceeds the limit, and never hand the oversized body to the app.

Bodies within the limit are buffered here (bounded by MAX_BODY_BYTES, so
this is cheap) and replayed to the downstream app through a synthetic
`receive`, so normal request parsing downstream is unaffected.
"""
import json
import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import config


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int | None = None):
        self.app = app
        self._max_bytes_override = max_bytes

    @property
    def max_bytes(self) -> int:
        return self._max_bytes_override or config.MAX_BODY_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not config.security_defences_enabled():
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope, send)
            return

        buffered: list[dict] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                buffered.append(message)
                break
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                # Stop reading now: never forward the oversized body, and
                # never ask the client for more of it.
                await self._reject(scope, send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive() -> dict:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = scope.setdefault("state", {}).get("request_id") or str(uuid.uuid4())
        body = json.dumps({
            "error": {
                "code": "PAYLOAD_TOO_LARGE",
                "message": f"Request body exceeds the {self.max_bytes}-byte limit.",
                "request_id": request_id,
            }
        }).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"x-request-id", request_id.encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
