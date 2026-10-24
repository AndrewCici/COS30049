"""Offline statistical fallback: a locally trained sklearn pipeline.

This is the Stage-2 model. It is small (a few MB), needs no network and no
GPU, and loads in well under a second — which is exactly what a fallback
must be. Training and evaluation live in backend/ml/; this class only loads
the frozen artifact and predicts.
"""
import json
from pathlib import Path

from ..model_integrity import verify_sha256
from .base import Detector

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_PATH = MODEL_DIR / "statistical_model.joblib"
META_PATH = MODEL_DIR / "statistical_model.meta.json"
HASH_PATH = MODEL_DIR / "statistical_model.sha256"


class StatisticalDetector(Detector):
    name = "statistical"
    model_name = "tfidf-stylometric-logreg"
    version = "unknown"

    def __init__(self):
        self._pipeline = None
        if META_PATH.exists():
            meta = json.loads(META_PATH.read_text())
            self.version = meta.get("version", "unknown")
            self.model_name = meta.get("model_name", self.model_name)

    def _load(self):
        if self._pipeline is None:
            import joblib  # deferred so probing availability stays cheap
            self._pipeline = joblib.load(MODEL_PATH)
        return self._pipeline

    def load_verified(self):
        """Load the pipeline, first checking its SHA-256 against the
        committed hash file. Called once at app startup so a corrupted or
        tampered model file is caught before any request is served."""
        if self._pipeline is None:
            verify_sha256(MODEL_PATH, HASH_PATH)
        return self._load()

    def available(self) -> bool:
        return MODEL_PATH.exists()

    def score_sentences(self, sentences: list[str]) -> list[float]:
        pipeline = self._load()
        probs = pipeline.predict_proba(sentences)  # class 1 == AI-generated
        return [float(p) for p in probs[:, 1]]
