#!/usr/bin/env python3
"""Offline detection-evasion experiment: how often does each perturbation
technique (homoglyph, invisible, fullwidth, combining, mixed), at three
intensities (10/25/50% per eligible character), flip a correctly-detected
AI-generated sentence to "human-made" -- with the normalisation defence
(backend/app/normalise.py) on and off.

Uses backend/ml/data/test_split.jsonl, the exact held-out test set the
statistical model was evaluated against for Assignment 2. Only label=1
(AI-generated) sentences the clean, unperturbed model already scores
correctly (>= the 0.5 verdict threshold) are eligible: a realistic
attacker already has text a detector would otherwise flag, and wants an
evasive rewrite of exactly that text to read as human-made.

5 independent seeds x 200 sentences per (technique, rate) combination =
1000 trials per condition, drawn once from a seeded sample of eligible
sentences (the same 1000-sentence pool for every technique/rate, so
results are an apples-to-apples comparison, not an artifact of which
sentences happened to be sampled). Reports "k of 1000" and a 95%
bootstrap confidence interval (2000 resamples, same method as
app.aggregate.bootstrap_ci) on the success rate, for both the defended
and undefended condition.

Usage (from the repository root, with backend/requirements*.txt and
requirements-dev.txt installed):
    python security/evasion/run_experiment.py
Writes security/evasion/results/experiment.json and prints the summary
table below to stdout; security/evasion/REPORT.md is written by hand
from that file's numbers, never fabricated.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))

from app.detectors.statistical import StatisticalDetector  # noqa: E402
from app.normalise import normalise_text  # noqa: E402
from perturb import TECHNIQUES, perturb  # noqa: E402

DATA = BACKEND / "ml" / "data" / "test_split.jsonl"
SEEDS = [1, 2, 3, 4, 5]
N_PER_SEED = 200
RATES = [0.10, 0.25, 0.50]
VERDICT_THRESHOLD = 0.5
# Fixed so the same 1000-sentence pool is used for every technique/rate
# combination -- any difference between conditions is then attributable
# to the technique, not to which sentences were sampled.
MASTER_SAMPLE_SEED = 20261106


def load_eligible_sentences(detector: StatisticalDetector) -> list[str]:
    candidates = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["label"] == 1 and len(row["text"]) >= 20:
                candidates.append(row["text"])
    scores = detector.score_sentences(candidates)
    return [t for t, s in zip(candidates, scores) if s >= VERDICT_THRESHOLD]


def sample_pool(eligible: list[str]) -> list[str]:
    rng = random.Random(MASTER_SAMPLE_SEED)
    pool_size = len(SEEDS) * N_PER_SEED
    if len(eligible) < pool_size:
        raise RuntimeError(f"Only {len(eligible)} eligible sentences; need {pool_size}.")
    return rng.sample(eligible, pool_size)


def bootstrap_ci(outcomes: list[int], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(outcomes)
    means = []
    for _ in range(n_boot):
        total = 0
        for _ in range(n):
            total += outcomes[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[min(int(0.975 * n_boot), n_boot - 1)]
    return lo, hi


def run() -> dict:
    detector = StatisticalDetector()
    detector.load_verified()

    eligible = load_eligible_sentences(detector)
    pool = sample_pool(eligible)
    print(f"{len(eligible)} eligible AI-generated sentences (correctly scored "
          f">= {VERDICT_THRESHOLD} by the clean model); sampled {len(pool)} "
          f"for this experiment.")

    results: dict = {
        "n_eligible": len(eligible),
        "pool_size": len(pool),
        "seeds": SEEDS,
        "n_per_seed": N_PER_SEED,
        "verdict_threshold": VERDICT_THRESHOLD,
        "conditions": {},
    }
    t0 = time.perf_counter()
    for technique in TECHNIQUES:
        for rate in RATES:
            key = f"{technique}_{int(rate * 100)}pct"
            undefended, defended = [], []
            idx = 0
            for seed in SEEDS:
                batch = pool[idx: idx + N_PER_SEED]
                idx += N_PER_SEED
                perturbed = [perturb(t, technique, rate, seed=seed * 1_000_000 + i)
                             for i, t in enumerate(batch)]
                off_scores = detector.score_sentences(perturbed)
                on_scores = detector.score_sentences(
                    [normalise_text(t).text for t in perturbed])
                undefended.extend(1 if s < VERDICT_THRESHOLD else 0 for s in off_scores)
                defended.extend(1 if s < VERDICT_THRESHOLD else 0 for s in on_scores)

            n_total = len(undefended)
            k_off, k_on = sum(undefended), sum(defended)
            ci_off = bootstrap_ci(undefended, seed=1)
            ci_on = bootstrap_ci(defended, seed=2)
            results["conditions"][key] = {
                "technique": technique, "rate": rate, "n": n_total,
                "undefended": {"k": k_off, "rate": k_off / n_total, "ci95": list(ci_off)},
                "defended": {"k": k_on, "rate": k_on / n_total, "ci95": list(ci_on)},
            }
            print(f"{key:>18}: undefended {k_off:4d}/{n_total} "
                  f"({k_off / n_total:5.1%}, CI {ci_off[0]:.1%}-{ci_off[1]:.1%})  |  "
                  f"defended {k_on:4d}/{n_total} "
                  f"({k_on / n_total:5.1%}, CI {ci_on[0]:.1%}-{ci_on[1]:.1%})")
    results["elapsed_s"] = round(time.perf_counter() - t0, 1)
    return results


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    results = run()
    out_path = RESULTS / "experiment.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nElapsed {results['elapsed_s']}s. Wrote {out_path}")


if __name__ == "__main__":
    main()
