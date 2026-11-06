#!/usr/bin/env python3
"""30 live evasion attempts through the real, running POST /api/v1/score
endpoint -- not a direct in-process call to the detector (that is what
run_experiment.py does, at much larger scale, offline). This script
exists to prove the same effect holds end-to-end through the actual HTTP
API: request body, middleware stack, Pydantic validation and all.

Each attempt sends a sentence drawn from the same eligible-AI-sentence
pool as run_experiment.py (held-out test sentences the clean model
already correctly flags as AI-generated), perturbed with one attack
technique at one rate, and records whether the API's verdict flipped to
"human-made". Run this script twice against two separately started
servers -- the same two-pass pattern security/dos/flood.py uses -- to
compare the undefended and defended condition:

    cd backend && NORMALISE_INPUT=off ../.venv/bin/uvicorn app.main:app --port 8000
    python security/evasion/live_attack.py --label undefended

    cd backend && ../.venv/bin/uvicorn app.main:app --port 8000   # defence on (default)
    python security/evasion/live_attack.py --label defended

Writes security/evasion/results/live_attack_<label>.csv and prints a
"k of 30" summary; security/evasion/REPORT.md quotes these two runs'
real output, not an assumption that they match run_experiment.py's
offline numbers (they should be close, since it is the same model and
defence code, but this is the check that confirms it rather than taking
it on faith).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
sys.path.insert(0, str(HERE))

from perturb import perturb  # noqa: E402

DATA = BACKEND / "ml" / "data" / "test_split.jsonl"
N = 30
TECHNIQUE = "mixed"
RATE = 0.25
# Different from run_experiment.py's MASTER_SAMPLE_SEED on purpose: this
# is a separate, smaller, independently-drawn sample, not a subset of
# that experiment's 1000, so the two don't share any sentence by
# construction and can't quietly validate each other's bug.
SAMPLE_SEED = 20261107


def load_candidates() -> list[str]:
    rows = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["label"] == 1 and len(row["text"]) >= 20:
                rows.append(row["text"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--label", required=True,
                    help="e.g. 'undefended' or 'defended' -- names the output CSV.")
    ap.add_argument("--technique", default=TECHNIQUE)
    ap.add_argument("--rate", type=float, default=RATE)
    args = ap.parse_args()

    candidates = load_candidates()
    rng = random.Random(SAMPLE_SEED)
    sample = rng.sample(candidates, N)

    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    successes = 0
    with httpx.Client(timeout=10.0) as client:
        for i, text in enumerate(sample):
            perturbed = perturb(text, args.technique, args.rate, seed=90_000 + i)
            r = client.post(f"{args.base_url}/api/v1/score", json={"text": perturbed})
            if r.status_code != 200:
                rows.append({"i": i, "status": r.status_code, "verdict": None,
                            "score": None, "evaded": False, "text": perturbed})
                continue
            body = r.json()
            verdict = body["document"]["verdict"]
            score = body["document"]["score"]
            evaded = verdict == "human-made"
            successes += evaded
            rows.append({"i": i, "status": 200, "verdict": verdict, "score": score,
                        "evaded": evaded, "text": perturbed})
            print(f"[{i + 1:2d}/{N}] score={score:.3f} verdict={verdict:12s} "
                  f"evaded={'YES' if evaded else 'no'}")

    print(f"\n{args.label}: evaded in {successes} of {N} attempts "
          f"({successes / N:.1%}) using '{args.technique}' at {args.rate:.0%}.")

    out_path = RESULTS / f"live_attack_{args.label}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["i", "status", "verdict", "score",
                                                "evaded", "text"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
