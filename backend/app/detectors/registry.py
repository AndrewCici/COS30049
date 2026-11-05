"""Detector registry and fallback chain.

`statistical` (the Assignment 2 logistic-regression model) is the default
and only detector in a standard install: it is small, needs no network or
GPU, and is loaded once at startup (see app.main's lifespan). The pretrained
HF transformer is opt-in via `AIDETECT_ENABLE_HF=1` — it needs torch and
transformers (requirements-optional.txt) and a ~500MB download, so it must
never be required just to run the app.

Resolution order (configurable via AIDETECT_METHOD):
    [hf-transformer, if enabled] -> statistical -> [mock, if AIDETECT_ALLOW_MOCK=1]

The chain is resolved lazily per process and re-probed only when the cached
choice becomes unavailable, so the common path costs nothing. The resolved
method is always reported in `meta.method` / `meta.fallback_used` — the UI
must be able to tell the user which model actually answered.
"""
import os

from ..config import enable_hf
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


def get(name: str) -> Detector:
    return _instances()[name]


def preferred_order() -> list[str]:
    forced = os.environ.get("AIDETECT_METHOD")
    if forced:
        return [forced]
    order = []
    if enable_hf():
        order.append("hf-transformer")
    order.append("statistical")
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
    """Status per detector in the active resolution chain, for /health.

    Only detectors that resolve() could actually choose are reported: the
    mock (unless AIDETECT_ALLOW_MOCK=1) and the HF transformer (unless
    AIDETECT_ENABLE_HF=1) are unreachable, so listing them as 'available'
    would misdescribe what can answer a request."""
    out = {}
    for name in preferred_order():
        det = _instances().get(name)
        if det is None:
            continue
        # Prefer a cheap probe (e.g. HF cache check) so /health never
        # triggers a model download.
        probe = getattr(det, "cached_locally", None) or det.available
        out[name] = probe()
    return out
