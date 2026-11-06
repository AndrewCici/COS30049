"""Security response headers (see security/misconfig/FINDINGS.md): present
on success, on every error status this app can return (413/422/500), and
specifically absent/different where a route needs it (the relaxed CSP on
/docs, Cache-Control: no-store only on /score). Also covers the
SECURITY_DEFENCES=off demo toggle and that no response carries two copies
of the same header, which a past version of the 413 path briefly did."""
import os

from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.main import app  # noqa: E402

client = TestClient(app)

_REQUIRED = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-resource-policy": "same-origin",
}


def _assert_security_headers(headers, *, csp_contains: str) -> None:
    lower = {k.lower(): v for k, v in headers.items()}
    for name, value in _REQUIRED.items():
        assert lower.get(name) == value, f"{name} missing or wrong: {lower.get(name)!r}"
    assert "permissions-policy" in lower
    csp = lower.get("content-security-policy", "")
    assert csp_contains in csp
    # base-uri/form-action have no fallback to default-src, so ZAP's
    # "Failure to Define Directive with No Fallback" check needs them
    # present explicitly on every response, not inferred from default-src.
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp


def test_headers_present_on_200():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    _assert_security_headers(r.headers, csp_contains="default-src 'none'")


def test_headers_present_on_413():
    r = client.post("/api/v1/score", json={"text": "word " * 20_000})
    assert r.status_code == 413
    _assert_security_headers(r.headers, csp_contains="default-src 'none'")


def test_headers_present_on_422():
    r = client.post("/api/v1/score", json={"text": "short"})
    assert r.status_code == 422
    _assert_security_headers(r.headers, csp_contains="default-src 'none'")


def test_headers_present_on_500(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("synthetic failure for the test")

    monkeypatch.setattr("app.main.split_sentences", boom)
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    r = no_raise_client.post("/api/v1/score", json={"text": "A perfectly normal sentence here."})
    assert r.status_code == 500
    _assert_security_headers(r.headers, csp_contains="default-src 'none'")


def test_no_duplicate_headers_on_413():
    # BodySizeLimitMiddleware used to set its own X-Request-ID, duplicating
    # the one RequestIDMiddleware (which wraps it) already adds.
    # Headers.keys()/.items() silently dedupe repeated header lines, so the
    # check needs multi_items(), which preserves every line as sent.
    r = client.post("/api/v1/score", json={"text": "word " * 20_000})
    assert r.status_code == 413
    names = [k.lower() for k, _ in r.headers.multi_items()]
    assert names.count("x-request-id") == 1


def test_docs_gets_relaxed_csp_for_swagger_ui():
    r = client.get("/docs")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    assert "cdn.jsdelivr.net" in csp
    assert "default-src 'none'" not in csp


def test_score_response_is_not_cacheable():
    r = client.post("/api/v1/score", json={"text": "A perfectly normal sentence here."})
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"


def test_health_response_has_no_cache_control_override():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert "cache-control" not in {k.lower() for k in r.headers}


def test_no_server_identification_header():
    r = client.get("/api/v1/health")
    assert "server" not in {k.lower() for k in r.headers}


def test_redoc_is_disabled():
    # Duplicates /docs against the same OpenAPI document and would need a
    # third external CSP origin (Google Fonts) for a page nothing links to.
    r = client.get("/redoc")
    assert r.status_code == 404


def test_headers_disabled_by_security_defences_off(monkeypatch):
    monkeypatch.setenv("SECURITY_DEFENCES", "off")
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    names = {k.lower() for k in r.headers}
    assert "x-content-type-options" not in names
    assert "content-security-policy" not in names
    assert "cross-origin-resource-policy" not in names
