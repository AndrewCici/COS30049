"""document.verdict / document.confidence: a binary call at threshold 0.5,
with confidence as the probability of the predicted class (not of
'ai-generated' specifically)."""
import os

from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.detectors.mock import MockDetector  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_verdict_and_confidence_match_document_score():
    text = ("The results were surprising to everyone involved. "
            "Furthermore, the methodology demonstrates significant improvements.")
    sents_text = [
        "The results were surprising to everyone involved.",
        "Furthermore, the methodology demonstrates significant improvements.",
    ]
    raw_scores = MockDetector().score_sentences(sents_text)

    r = client.post("/api/v1/score", json={"text": text})
    assert r.status_code == 200
    doc = r.json()["document"]

    if doc["score"] >= 0.5:
        assert doc["verdict"] == "ai-generated"
        assert abs(doc["confidence"] - doc["score"]) < 1e-9
    else:
        assert doc["verdict"] == "human-made"
        assert abs(doc["confidence"] - (1.0 - doc["score"])) < 1e-9
    assert len(raw_scores) == 2  # sanity: mock detector is deterministic


def test_confidence_is_always_at_least_half():
    r = client.post("/api/v1/score", json={
        "text": "A short but valid test sentence. Another one follows here.",
    })
    assert r.json()["document"]["confidence"] >= 0.5
