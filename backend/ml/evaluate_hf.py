"""Evaluate the primary HuggingFace detector on the same held-out split the
statistical model was tested on (a balanced subsample — CPU transformer
inference over the full 16k test sentences would take hours for no extra
statistical power).

Pass a large n (e.g. 8000) to score the *entire* test split, so every model
in the comparison table is evaluated on the identical sentences.

Caveat for the report: this pretrained detector was trained on HC3, so its
HC3 results are not "unseen data"; only the DAIGT rows (see per_source) are.

Usage:  python -m ml.evaluate_hf [n_per_class=750]
"""
import json
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.detectors.hf_detector import HFDetector  # noqa: E402
from ml.train import DATA, MODELS, SEED, evaluate  # noqa: E402


def main(n_per_class: int = 750):
    rows = [json.loads(l) for l in open(DATA / "test_split.jsonl")]
    rng = random.Random(SEED)
    by_class = {0: [r for r in rows if r["label"] == 0],
                1: [r for r in rows if r["label"] == 1]}
    sample = []
    for cls_rows in by_class.values():
        rng.shuffle(cls_rows)
        sample.extend(cls_rows[:n_per_class])
    rng.shuffle(sample)

    det = HFDetector()
    assert det.available(), "HF model not available"
    print(f"Scoring {len(sample)} sentences with {det.model_name}…")
    probs = det.score_sentences([r["text"] for r in sample])
    metrics = evaluate([r["label"] for r in sample], probs)
    print(json.dumps(metrics, indent=2))

    # Same breakdown as Table 3 in train.py: results per source corpus.
    per_source = {}
    for src in sorted({r["source"] for r in sample if "source" in r}):
        idx = [i for i, r in enumerate(sample) if r.get("source") == src]
        ys = [sample[i]["label"] for i in idx]
        if len(set(ys)) == 2:
            per_source[src] = evaluate(ys, [probs[i] for i in idx])

    out = MODELS / "hf_eval.json"
    out.write_text(json.dumps(
        {"model": det.model_name, "n_per_class": n_per_class,
         "metrics": metrics, "per_source": per_source}, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 750)
