"""BodySizeLimitMiddleware: a declared-too-large Content-Length is rejected
without ever calling receive(); a body that turns out too large while
streaming (no/false Content-Length, or chunked) is rejected the instant the
running total crosses the limit, without reading further or forwarding it
downstream. Unit tests drive the ASGI interface directly for precise
control over what the "client" sends; the integration tests at the bottom
exercise the real app over HTTP."""
import json
import os

import pytest

from app.security.body_limit import BodySizeLimitMiddleware


def _scope(headers: dict[str, str] | None = None) -> dict:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    return {"type": "http", "method": "POST", "path": "/x", "headers": raw_headers}


class _Recorder:
    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None

    @property
    def body(self) -> bytes:
        return b"".join(
            m.get("body", b"") for m in self.messages if m["type"] == "http.response.body"
        )


class _DownstreamApp:
    """Records every message its receive() returns, and what it was given
    to send, so tests can see exactly what crossed the middleware boundary."""

    def __init__(self):
        self.received: list[dict] = []
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        while True:
            message = await receive()
            self.received.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _chunks(parts: list[bytes]):
    """A receive() that yields `parts` as successive http.request chunks."""
    remaining = list(parts)

    async def receive():
        if remaining:
            body = remaining.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(remaining)}
        raise AssertionError("receive() called past the end of the body")

    return receive


@pytest.mark.anyio
async def test_declared_content_length_too_large_rejected_without_reading(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    downstream = _DownstreamApp()
    mw = BodySizeLimitMiddleware(downstream, max_bytes=10)

    async def receive_should_not_be_called():
        raise AssertionError("receive() must not be called once Content-Length "
                             "alone proves the body is too large")

    send = _Recorder()
    await mw(_scope({"content-length": "1000"}), receive_should_not_be_called, send)

    assert send.status == 413
    assert not downstream.called
    body = json.loads(send.body)
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "request_id" in body["error"]


@pytest.mark.anyio
async def test_streamed_body_exceeding_limit_stops_reading_and_rejects(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    downstream = _DownstreamApp()
    mw = BodySizeLimitMiddleware(downstream, max_bytes=10)

    # No (or a false) Content-Length -- the only way to know this is too
    # large is to count bytes as they stream in. Five chunks are queued;
    # the limit (10 bytes) is crossed partway through, so chunks after that
    # point must never be consumed.
    receive = _chunks([b"123456", b"789012", b"345678", b"901234", b"567890"])
    send = _Recorder()
    await mw(_scope(), receive, send)

    assert send.status == 413
    assert not downstream.called


@pytest.mark.anyio
async def test_body_within_limit_is_replayed_unchanged_to_the_app(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    downstream = _DownstreamApp()
    mw = BodySizeLimitMiddleware(downstream, max_bytes=1024)

    receive = _chunks([b"hello ", b"world"])
    send = _Recorder()
    await mw(_scope(), receive, send)

    assert downstream.called
    assert b"".join(m.get("body", b"") for m in downstream.received) == b"hello world"
    assert send.status == 200


@pytest.mark.anyio
async def test_disabled_by_security_defences_off_passes_everything_through(monkeypatch):
    monkeypatch.setenv("SECURITY_DEFENCES", "off")
    downstream = _DownstreamApp()
    mw = BodySizeLimitMiddleware(downstream, max_bytes=10)

    receive = _chunks([b"x" * 1000])
    send = _Recorder()
    await mw(_scope({"content-length": "1000"}), receive, send)

    assert downstream.called
    assert send.status == 200


# --- integration: the real app over HTTP -----------------------------------

os.environ["AIDETECT_METHOD"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_oversized_request_rejected_413_over_http():
    r = client.post("/api/v1/score", json={"text": "word " * 20_000})
    assert r.status_code == 413
    body = r.json()
    assert body["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_oversized_request_413_still_carries_cors_header():
    r = client.post(
        "/api/v1/score",
        json={"text": "word " * 20_000},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_normal_sized_request_unaffected():
    r = client.post("/api/v1/score", json={"text": "A normal short passage. Another sentence."})
    assert r.status_code == 200
