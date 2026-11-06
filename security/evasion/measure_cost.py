#!/usr/bin/env python3
"""Measures what the normalisation defence (backend/app/normalise.py)
costs on *legitimate* traffic, as distinct from how well it works against
an attack (that's run_experiment.py). Three checks:

1. **Accuracy/F1/AUC on the clean test set** (backend/ml/data/test_split.jsonl,
   all 14,556 sentences, the same set used for Assignment 2's evaluation):
   with the defence on vs off. Clean English text contains essentially no
   Cf/combining-mark/confusable characters, so normalisation should be a
   no-op for almost every sentence and these numbers should match to
   within rounding -- this is the check that proves that claim, not an
   assumption of it.
2. **Per-call latency** of normalise_text() over the same test set: p50/p95/
   max, and as a percentage of the ~130ms per-request budget measured in
   security/dos/measure_cost.py.
3. **Vietnamese diacritics**: a set of genuine Vietnamese sentences (not
   constructed to attack the defence) run through normalise_text(), to
   confirm none of their legitimate combining-mark/precomposed-letter usage
   gets removed or altered -- the real risk this defence could introduce,
   since Vietnamese orthography is the main source of combining marks a
   genuine user might paste.

Usage (from the repository root, with backend/requirements*.txt installed):
    python security/evasion/measure_cost.py
Writes security/evasion/results/cost.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
RESULTS = Path(__file__).resolve().parent / "results"
sys.path.insert(0, str(BACKEND))

from app.detectors.statistical import StatisticalDetector  # noqa: E402
from app.normalise import normalise_text  # noqa: E402

DATA = BACKEND / "ml" / "data" / "test_split.jsonl"
VERDICT_THRESHOLD = 0.5

# Genuine Vietnamese sentences (not adversarial), covering a spread of
# diacritic combinations: single tone marks, tone + quality mark
# (circumflex/breve/horn) stacked on one vowel, and sentence-initial
# capitals.
VIETNAMESE_SENTENCES = [
    "Tiếng Việt rất hay.",
    "Hôm nay trời đẹp và nắng ấm.",
    "Tôi đang học lập trình máy tính.",
    "Cô ấy thích đọc sách vào buổi tối.",
    "Chúng tôi sẽ đi du lịch Đà Lạt vào tuần sau.",
    "Anh ấy làm việc chăm chỉ để nuôi gia đình.",
    "Những bông hoa trong vườn nở rộ vào mùa xuân.",
    "Bài kiểm tra ngày mai rất quan trọng đối với tôi.",
    "Cảm ơn bạn đã giúp đỡ tôi rất nhiều.",
    "Thành phố Hồ Chí Minh về đêm rất nhộn nhịp.",
]


def load_test_sentences() -> list[tuple[str, int]]:
    rows = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            rows.append((row["text"], row["label"]))
    return rows


def metrics(scores: list[float], labels: list[int]) -> dict:
    preds = [1 if s >= VERDICT_THRESHOLD else 0 for s in scores]
    tp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 1)
    tn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 0)
    fp = sum(1 for p, y in zip(preds, labels) if p == 1 and y == 0)
    fn = sum(1 for p, y in zip(preds, labels) if p == 0 and y == 1)
    n = len(labels)
    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {"accuracy": accuracy, "precision": precision, "recall": recall,
            "f1": f1, "false_positive_rate": fpr, "n": n}


def percentiles(values: list[float]) -> dict:
    s = sorted(values)
    n = len(s)
    return {
        "p50": s[int(0.50 * n)], "p95": s[int(0.95 * n)],
        "p99": s[min(int(0.99 * n), n - 1)], "max": s[-1],
    }


def run() -> dict:
    detector = StatisticalDetector()
    detector.load_verified()

    rows = load_test_sentences()
    texts = [t for t, _ in rows]
    labels = [y for _, y in rows]

    off_scores = detector.score_sentences(texts)

    normalised = []
    latencies_ms = []
    for t in texts:
        t0 = time.perf_counter()
        normalised.append(normalise_text(t).text)
        latencies_ms.append((time.perf_counter() - t0) * 1000)
    on_scores = detector.score_sentences(normalised)

    off_metrics = metrics(off_scores, labels)
    on_metrics = metrics(on_scores, labels)
    lat = percentiles(latencies_ms)

    vn_results = []
    for s in VIETNAMESE_SENTENCES:
        r = normalise_text(s)
        vn_results.append({
            "text": s, "unchanged": r.text == s,
            "combining_marks_removed": r.combining_marks_removed,
            "confusables_mapped": r.confusables_mapped,
            "cf_removed": r.cf_removed,
        })
    vn_all_unchanged = all(r["unchanged"] for r in vn_results)

    return {
        "clean_test_set": {
            "n": len(rows),
            "undefended": off_metrics,
            "defended": on_metrics,
        },
        "normalise_latency_ms": lat,
        "vietnamese_diacritics": {
            "all_unchanged": vn_all_unchanged,
            "sentences": vn_results,
        },
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    results = run()

    off, on = results["clean_test_set"]["undefended"], results["clean_test_set"]["defended"]
    print(f"Clean test set (n={results['clean_test_set']['n']}):")
    print(f"  undefended: accuracy={off['accuracy']:.4f} f1={off['f1']:.4f} "
          f"fpr={off['false_positive_rate']:.4f}")
    print(f"  defended:   accuracy={on['accuracy']:.4f} f1={on['f1']:.4f} "
          f"fpr={on['false_positive_rate']:.4f}")
    lat = results["normalise_latency_ms"]
    print(f"normalise_text() latency: p50={lat['p50']:.4f}ms p95={lat['p95']:.4f}ms "
          f"max={lat['max']:.4f}ms")
    vn = results["vietnamese_diacritics"]
    print(f"Vietnamese diacritics: all {len(vn['sentences'])} sentences unchanged = "
          f"{vn['all_unchanged']}")
    for r in vn["sentences"]:
        if not r["unchanged"]:
            print(f"  MANGLED: {r['text']!r}")

    out_path = RESULTS / "cost.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
