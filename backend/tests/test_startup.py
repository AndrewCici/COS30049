"""Startup-time integrity checks: the committed statistical-model artifact
must match its recorded SHA-256 before the app will serve any request.

These tests enter the app as a context manager (`with TestClient(app)`),
which is the only way Starlette actually runs ASGI lifespan events -- a
bare `TestClient(app)` (used by the other test modules, for speed) never
triggers startup/shutdown at all."""
import pytest
from fastapi.testclient import TestClient

from app.detectors import registry
from app.main import app
from app.model_integrity import ModelIntegrityError


def test_statistical_model_passes_integrity_check_at_startup(monkeypatch):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)
    with TestClient(app) as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["active_method"] == "statistical"


def test_tampered_hash_prevents_startup(monkeypatch, tmp_path):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)

    det = registry.get("statistical")
    bad_hash = tmp_path / "statistical_model.sha256"
    bad_hash.write_text("0" * 64 + "  statistical_model.joblib\n")
    monkeypatch.setattr("app.detectors.statistical.HASH_PATH", bad_hash)
    # Force re-verification: a prior test in this process may already have
    # cached the real pipeline on this singleton.
    monkeypatch.setattr(det, "_pipeline", None)

    with pytest.raises(ModelIntegrityError):
        with TestClient(app):
            pass


def test_missing_hash_file_prevents_startup(monkeypatch, tmp_path):
    monkeypatch.delenv("AIDETECT_METHOD", raising=False)
    monkeypatch.delenv("AIDETECT_ENABLE_HF", raising=False)

    det = registry.get("statistical")
    missing_hash = tmp_path / "does_not_exist.sha256"
    monkeypatch.setattr("app.detectors.statistical.HASH_PATH", missing_hash)
    monkeypatch.setattr(det, "_pipeline", None)

    with pytest.raises(ModelIntegrityError):
        with TestClient(app):
            pass
