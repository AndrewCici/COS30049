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
    insts = registry._instances()
    with patch.object(type(insts["hf-transformer"]), "available", return_value=False), \
         patch.object(type(insts["statistical"]), "available", return_value=False):
        r = make_client().post("/api/v1/score", json={"text": TEXT})
        assert r.status_code == 503
        assert "detection method" in r.json()["detail"].lower()


def test_forced_method_respected(monkeypatch):
    monkeypatch.setenv("AIDETECT_METHOD", "mock")
    r = make_client().post("/api/v1/score", json={"text": TEXT})
    assert r.json()["meta"]["method"] == "mock"
    assert r.json()["meta"]["fallback_used"] is False
