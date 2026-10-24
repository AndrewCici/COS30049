"""Shared accessor for backend/models/statistical_model.meta.json.

Kept separate from StatisticalDetector so /model-info can read the full
training/evaluation summary without coupling to the detector's narrower
(name, version) parsing.
"""
import json
from pathlib import Path

META_PATH = Path(__file__).resolve().parent.parent / "models" / "statistical_model.meta.json"


def load_meta() -> dict | None:
    if not META_PATH.exists():
        return None
    return json.loads(META_PATH.read_text())
