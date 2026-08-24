"""Detector registry and fallback chain.

Resolution order (configurable via AIDETECT_METHOD):
    hf-transformer  →  statistical  →  mock (only if AIDETECT_ALLOW_MOCK=1)

The chain is resolved lazily per process and re-probed only when the cached
choice becomes unavailable, so the common path costs nothing. The resolved
method is always reported in `meta.method` / `meta.fallback_used` — the UI
must be able to tell the user which model actually answered.
"""
import os

from .base import Detector
from .hf_detector import HFDetector
from .mock import MockDetector
from .statistical import StatisticalDetector

_detectors: dict[str, Detector] = {}


def _instances() -> dict[str, Detector]:
    if not _detectors:
        _detectors["hf-transformer"] = HFDetector()
        _detectors["statistical"] = StatisticalDetector()
        _detectors["mock"] = MockDetector()
    return _detectors


def preferred_order() -> list[str]:
    forced = os.environ.get("AIDETECT_METHOD")
    if forced:
        return [forced]
    order = ["hf-transformer", "statistical"]
    if os.environ.get("AIDETECT_ALLOW_MOCK") == "1":
        order.append("mock")
    return order


def resolve() -> tuple[Detector, bool]:
    """Return (detector, fallback_used)."""
    order = preferred_order()
    for i, name in enumerate(order):
        det = _instances().get(name)
        if det is None:
            continue
        if det.available():
            return det, i > 0
    raise RuntimeError(
        "No detection method is available. Train the statistical model "
        "(backend/ml/train.py) or allow the mock (AIDETECT_ALLOW_MOCK=1)."
    )


def availability() -> dict[str, bool]:
    out = {}
    for name, det in _instances().items():
        # Prefer a cheap probe (e.g. HF cache check) so /health never
        # triggers a model download.
        probe = getattr(det, "cached_locally", None) or det.available
        out[name] = probe()
    return out
