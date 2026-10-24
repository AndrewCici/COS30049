"""Inference runs off the event loop with a timeout backstop, and /health
never waits behind it. These are integration tests against the real app
(not the limiter/middleware in isolation) because the property under test
-- that one slow /score call does not block a concurrent /health call -- is
exactly the interaction between threads and the event loop that a unit test
of either piece alone cannot show."""
import os
import threading
import time

os.environ["AIDETECT_METHOD"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402
from app.detectors.mock import MockDetector  # noqa: E402

client = TestClient(main_module.app)


def test_inference_timeout_returns_503(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    monkeypatch.setattr("app.main.config.INFERENCE_TIMEOUT_S", 0.05)

    class SlowDetector(MockDetector):
        def score_sentences(self, sentences):
            time.sleep(0.3)
            return super().score_sentences(sentences)

    monkeypatch.setattr(
        "app.main.registry.resolve", lambda: (SlowDetector(), False)
    )
    r = client.post("/api/v1/score", json={"text": "A normal passage. Another sentence here."})
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "INFERENCE_TIMEOUT"
    assert "retry-after" in {k.lower() for k in r.headers}


def test_health_responds_promptly_while_a_slow_score_request_is_in_flight(monkeypatch):
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)

    class SlowDetector(MockDetector):
        def score_sentences(self, sentences):
            time.sleep(1.0)
            return super().score_sentences(sentences)

    monkeypatch.setattr(
        "app.main.registry.resolve", lambda: (SlowDetector(), False)
    )

    slow_done = threading.Event()

    def run_slow_score():
        client.post("/api/v1/score", json={"text": "A normal passage. Another sentence here."})
        slow_done.set()

    t = threading.Thread(target=run_slow_score)
    t.start()
    time.sleep(0.1)  # let the slow request actually enter the handler first

    t0 = time.perf_counter()
    r = client.get("/api/v1/health")
    elapsed = time.perf_counter() - t0

    assert r.status_code == 200
    assert elapsed < 0.3  # far under the 1s the slow /score call is sleeping for
    assert not slow_done.is_set()  # proves the slow call was genuinely still running

    t.join(timeout=5)
