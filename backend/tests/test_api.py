"""API contract tests. Run against the mock detector so they are fast and
model-independent — the whole point of the contract is that it holds no
matter which detector answers."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.main import app  # noqa: E402

client = TestClient(app)

TEXT = ("The results were surprising to everyone involved. "
        "Furthermore, the methodology demonstrates significant improvements. "
        "My dog ate my homework last week, no joke. "
        "In conclusion, these findings suggest broad applicability.")


def test_score_contract():
    r = client.post("/api/v1/score", json={"text": TEXT})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"sentences", "document", "meta"}

    for s in body["sentences"]:
        assert 0.0 <= s["score"] <= 1.0
        assert s["band"] in {"low", "medium", "high"}
        assert TEXT[s["start"]:s["end"]] == s["text"]

    doc = body["document"]
    assert 0.0 <= doc["ci_low"] <= doc["score"] <= doc["ci_high"] <= 1.0
    assert doc["confidence_level"] == 0.95
    assert doc["sentence_count"] == len(body["sentences"]) == 4

    meta = body["meta"]
    assert meta["method"] == "mock"
    assert meta["fallback_used"] is False
    assert "bands" in meta


def test_band_thresholds_consistent():
    r = client.post("/api/v1/score", json={"text": TEXT})
    body = r.json()
    bands = body["meta"]["bands"]
    for s in body["sentences"]:
        if s["score"] < bands["low_below"]:
            assert s["band"] == "low"
        elif s["score"] >= bands["high_at_or_above"]:
            assert s["band"] == "high"
        else:
            assert s["band"] == "medium"


def test_deterministic_for_same_input():
    a = client.post("/api/v1/score", json={"text": TEXT}).json()
    b = client.post("/api/v1/score", json={"text": TEXT}).json()
    assert a["document"] == b["document"]
    assert a["sentences"] == b["sentences"]


def test_short_text_warns():
    r = client.post("/api/v1/score", json={"text": "One tiny sentence."})
    assert r.status_code == 200
    assert any("short" in w.lower() for w in r.json()["meta"]["warnings"])


def test_empty_text_rejected():
    assert client.post("/api/v1/score", json={"text": ""}).status_code == 422


def test_no_sentences_rejected():
    r = client.post("/api/v1/score", json={"text": "!!! ??? ..."})
    assert r.status_code == 422
    assert "sentence" in r.json()["detail"].lower()


def test_too_long_rejected():
    r = client.post("/api/v1/score", json={"text": "word " * 20000})
    assert r.status_code == 422


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["active_method"] == "mock"


@pytest.mark.skipif(
    not os.path.exists(os.path.join(os.path.dirname(__file__), "..",
                                    "models", "statistical_model.joblib")),
    reason="statistical model not trained yet",
)
def test_statistical_detector_scores_sanely():
    from app.detectors.statistical import StatisticalDetector
    det = StatisticalDetector()
    scores = det.score_sentences([
        "lol yeah i dunno, my cat just knocked the mug off the table again.",
        "Furthermore, it is important to note that artificial intelligence "
        "demonstrates significant potential across numerous industries.",
    ])
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[1] > scores[0]  # AI-flavoured prose should score higher
