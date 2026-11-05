"""Fallback-chain behaviour: the API contract must hold regardless of which
detector answers, and the response must disclose which one did."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.detectors import registry
from app.main import app

TEXT = ("The committee reviewed all submissions carefully. "
        "Results will be announced next week to all participants. "
        "Everyone seemed pretty relaxed about the timeline.")


def make_client():
    return TestClient(app)


def test_falls_back_to_statistical_when_hf_unavailable(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.setenv("AIDETECT_ALLOW_MOCK", "1")
    monkeypatch.setenv("AIDETECT_ENABLE_HF", "1")
    hf = registry._instances()["hf-transformer"]
    stat = registry._instances()["statistical"]
    with patch.object(type(hf), "available", return_value=False):
        r = make_client().post("/api/v1/score", json={"text": TEXT})
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["method"] in {"statistical", "mock"}
        assert meta["fallback_used"] is True
        if meta["method"] == "statistical":
            assert stat.available()
        assert any("unavailable" in w for w in meta["warnings"])


def test_503_when_nothing_available(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ALLOW_MOCK", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)
    insts = registry._instances()
    with patch.object(type(insts["hf-transformer"]), "available", return_value=False), \
         patch.object(type(insts["statistical"]), "available", return_value=False):
        r = make_client().post("/api/v1/score", json={"text": TEXT})
        assert r.status_code == 503
        body = r.json()
        assert "detection method" in body["error"]["message"].lower()
        assert body["error"]["code"] == "DETECTOR_UNAVAILABLE"


def test_forced_method_respected(monkeypatch):
    monkeypatch.setenv("AIDETECT_METHOD", "mock")
    r = make_client().post("/api/v1/score", json={"text": TEXT})
    assert r.json()["meta"]["method"] == "mock"
    assert r.json()["meta"]["fallback_used"] is False


def test_hf_excluded_from_chain_by_default(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)
    assert registry.preferred_order() == ["statistical"]
    r = make_client().get("/api/v1/health")
    assert "hf-transformer" not in r.json()["available_methods"]


def test_hf_opt_in_via_env_flag(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.setenv("AIDETECT_ENABLE_HF", "1")
    assert registry.preferred_order()[0] == "hf-transformer"


def test_statistical_is_the_unflagged_default_not_a_fallback(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)
    r = make_client().post("/api/v1/score", json={"text": TEXT})
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["method"] == "statistical"
    assert meta["fallback_used"] is False


def test_health_lists_only_detectors_in_the_chain(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ALLOW_MOCK", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)
    from app.detectors import registry
    assert set(registry.availability()) == {"statistical"}
    monkeypatch.setenv("AIDETECT_ALLOW_MOCK", "1")
    assert set(registry.availability()) == {"statistical", "mock"}
