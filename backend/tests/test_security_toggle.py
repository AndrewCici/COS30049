"""SECURITY_DEFENCES=off is the escape hatch the DoS attack scripts use to
record "attack succeeds without defence": it must actually remove the
sentence-count cap (the body-size middleware and the limiter are covered by
their own dedicated tests). Default (unset, or any value other than "off")
must keep the cap enforced."""
import os

os.environ["AIDETECT_METHOD"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import MAX_SENTENCES  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

_MANY_SENTENCES_TEXT = ("This is one short sentence. " * (MAX_SENTENCES + 50))[:11_999]


def test_too_many_sentences_enforced_by_default(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    r = client.post("/api/v1/score", json={"text": _MANY_SENTENCES_TEXT})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "TOO_MANY_SENTENCES"


def test_too_many_sentences_cap_lifted_when_defences_off(monkeypatch):
    monkeypatch.setenv("SECURITY_DEFENCES", "off")
    r = client.post("/api/v1/score", json={"text": _MANY_SENTENCES_TEXT})
    assert r.status_code == 200
    assert r.json()["document"]["sentence_count"] > MAX_SENTENCES
