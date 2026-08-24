"""Document-level aggregation: length-weighted mean + bootstrap 95% CI.

Why a bootstrap instead of a normal-approximation interval:
- sentence scores are bounded in [0, 1] and frequently bimodal (a document
  that is half human, half AI has scores clustered near both ends), so a
  Gaussian standard-error interval is a poor fit and can exceed [0, 1];
- documents often have very few sentences, where asymptotic formulas break;
- the percentile bootstrap needs no distributional assumption and its
  interval is always within the observed score range.

The resampling is seeded from the score vector itself so the same input
always yields the same interval (determinism is a UX requirement: users
re-analysing unchanged text must not watch numbers wobble — Nielsen #4).
"""
import hashlib

import numpy as np

N_BOOTSTRAP = 2000


def weighted_mean(scores: list[float], weights: list[float]) -> float:
    w = np.asarray(weights, dtype=float)
    s = np.asarray(scores, dtype=float)
    if w.sum() == 0:
        return float(s.mean()) if len(s) else 0.0
    return float(np.dot(s, w) / w.sum())


def bootstrap_ci(
    scores: list[float],
    weights: list[float],
    confidence: float = 0.95,
    n_boot: int = N_BOOTSTRAP,
) -> tuple[float, float]:
    """Percentile-bootstrap CI for the length-weighted mean sentence score.

    Sentences are resampled with replacement; each draw keeps its weight, so
    the statistic recomputed per replicate is the same weighted mean the
    point estimate uses.
    """
    s = np.asarray(scores, dtype=float)
    w = np.asarray(weights, dtype=float)
    n = len(s)
    if n == 0:
        return (0.0, 0.0)
    if n == 1:
        # One sentence: no resampling distribution exists. Report the widest
        # honest interval around the point estimate given the [0,1] bound —
        # the UI pairs this with a "very short text" warning.
        return (max(0.0, s[0] - 0.25), min(1.0, s[0] + 0.25))

    seed = int.from_bytes(
        hashlib.sha256(np.round(s, 6).tobytes()).digest()[:4], "big"
    )
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    rs, rw = s[idx], w[idx]
    means = (rs * rw).sum(axis=1) / np.maximum(rw.sum(axis=1), 1e-9)
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(means, [alpha, 1.0 - alpha])
    return (float(lo), float(hi))


def document_band(doc_score: float, sentence_bands: list[str]) -> str:
    """Document band, with 'mixed' when sentences disagree strongly.

    A document averaging 0.5 because *every* sentence is ~0.5 ("medium") and
    one averaging 0.5 because half the sentences are ~0.9 and half ~0.1 are
    different situations; the second is reported as 'mixed' so the summary
    does not mislead (Nielsen #1/#2).
    """
    from .schemas import band_for

    if sentence_bands and "high" in sentence_bands and "low" in sentence_bands:
        highs = sentence_bands.count("high") / len(sentence_bands)
        lows = sentence_bands.count("low") / len(sentence_bands)
        if highs >= 0.25 and lows >= 0.25:
            return "mixed"
    return band_for(doc_score)
