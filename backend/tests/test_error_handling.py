"""The shared `{"error": {"code", "message", "request_id"}}` envelope must
hold for every error status the API returns, and a 500 must never leak a
traceback. Also covers the CORS origin allow-list."""
import os

from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.main import app  # noqa: E402

client = TestClient(app)


def _assert_error_envelope(body: dict, code: str | None = None) -> None:
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "request_id"}
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["request_id"], str) and error["request_id"]
    if code:
        assert error["code"] == code


def test_404_uses_error_envelope():
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    _assert_error_envelope(r.json(), code="NOT_FOUND")


def test_422_validation_error_uses_error_envelope_and_names_field():
    r = client.post("/api/v1/score", json={"text": 12345})  # wrong type
    assert r.status_code == 422
    body = r.json()
    _assert_error_envelope(body, code="VALIDATION_ERROR")
    assert "text" in body["error"]["message"]


def test_too_short_text_rejected_with_error_envelope():
    r = client.post("/api/v1/score", json={"text": "short"})
    assert r.status_code == 422
    _assert_error_envelope(r.json(), code="VALIDATION_ERROR")


def test_whitespace_only_text_rejected():
    r = client.post("/api/v1/score", json={"text": " " * 25})
    assert r.status_code == 422
    _assert_error_envelope(r.json(), code="VALIDATION_ERROR")


def test_too_many_sentences_rejected():
    text = "This is one short sentence. " * 400  # well past MAX_SENTENCES
    r = client.post("/api/v1/score", json={"text": text[:11_999]})
    assert r.status_code == 422
    _assert_error_envelope(r.json(), code="TOO_MANY_SENTENCES")


def test_forced_500_uses_error_envelope_without_traceback(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("synthetic failure for the test")

    monkeypatch.setattr("app.main.split_sentences", boom)
    # The server-side exception handler converts this to a 500 response, but
    # Starlette's ServerErrorMiddleware also re-raises it afterwards so the
    # ASGI server can log it; TestClient must not treat that re-raise as a
    # test failure.
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    r = no_raise_client.post("/api/v1/score", json={"text": "A perfectly normal sentence here."})
    assert r.status_code == 500
    body = r.json()
    _assert_error_envelope(body, code="INTERNAL_ERROR")
    raw = r.text
    assert "Traceback" not in raw
    assert "synthetic failure" not in raw
    assert "boom" not in raw


def test_every_response_carries_a_request_id_header():
    r = client.get("/api/v1/health")
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_disallowed_cors_origin_gets_no_cors_header():
    r = client.get("/api/v1/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_allowed_cors_origin_gets_cors_header():
    r = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
