"""Stage-1 mock detector.

Deterministic pseudo-scores derived from a hash of each sentence: the same
input always produces the same output (so the prototype feels like a real
tool and UI states are reproducible in demos/tests), and scores spread
across the whole [0, 1] range so every UI state — low/medium/high bands,
mixed documents — can be exercised before any model exists.
"""
import hashlib

from .base import Detector


class MockDetector(Detector):
    name = "mock"
    model_name = "deterministic-hash-mock"
    version = "1.0"

    def score_sentences(self, sentences: list[str]) -> list[float]:
        out = []
        for s in sentences:
            h = hashlib.sha256(s.strip().lower().encode()).digest()
            out.append(int.from_bytes(h[:4], "big") / 0xFFFFFFFF)
        return out
