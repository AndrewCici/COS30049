from app.aggregate import bootstrap_ci, document_band, weighted_mean


def test_weighted_mean_favours_long_sentences():
    # 90-word AI-ish sentence vs 10-word human-ish sentence
    assert weighted_mean([0.9, 0.1], [90, 10]) > 0.8
    assert abs(weighted_mean([0.5, 0.5], [3, 97]) - 0.5) < 1e-9


def test_ci_contains_point_estimate_and_stays_in_bounds():
    scores = [0.1, 0.9, 0.5, 0.7, 0.3, 0.8]
    weights = [10, 20, 15, 5, 30, 20]
    m = weighted_mean(scores, weights)
    lo, hi = bootstrap_ci(scores, weights)
    assert 0.0 <= lo <= m <= hi <= 1.0
    assert hi - lo > 0  # heterogeneous scores → non-degenerate interval


def test_ci_deterministic():
    scores, weights = [0.2, 0.6, 0.9], [10.0, 12.0, 8.0]
    assert bootstrap_ci(scores, weights) == bootstrap_ci(scores, weights)


def test_ci_narrow_when_scores_agree():
    lo_w, hi_w = bootstrap_ci([0.1, 0.9, 0.2, 0.8, 0.15, 0.85], [10] * 6)
    lo_n, hi_n = bootstrap_ci([0.5, 0.52, 0.48, 0.51, 0.49, 0.5], [10] * 6)
    assert (hi_n - lo_n) < (hi_w - lo_w)


def test_single_sentence_gets_wide_interval():
    lo, hi = bootstrap_ci([0.7], [12])
    assert hi - lo >= 0.4
    assert 0.0 <= lo <= 0.7 <= hi <= 1.0


def test_document_band_mixed():
    assert document_band(0.5, ["high", "high", "low", "low"]) == "mixed"
    assert document_band(0.5, ["medium"] * 4) == "medium"
    assert document_band(0.9, ["high"] * 4) == "high"
    assert document_band(0.1, ["low"] * 4) == "low"
