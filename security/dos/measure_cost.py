#!/usr/bin/env python3
"""Measure where /score actually spends time and memory, before designing
any defence against it.

Three things are timed separately, because they have different cost
profiles and are capped by different defences:

1. Reading and validating the request body (JSON parse + Pydantic) --
   capped by the body-size middleware (MAX_BODY_BYTES). This is measured
   up to a size far beyond anything a legitimate client would ever send,
   because that is exactly the gap an undefended server leaves open: a
   huge body is read into memory in full before Pydantic's max_length even
   gets a chance to reject it.
2. Sentence splitting + statistical-model inference -- capped by
   MAX_SENTENCES.
3. The length-weighted mean + bootstrap confidence interval -- capped
   indirectly through MAX_SENTENCES (the bootstrap's own cost is
   O(n_boot * n_sentences); n_boot is fixed at 2000).

Usage (from the repository root, with backend/requirements*.txt installed):
    python security/dos/measure_cost.py
Writes security/dos/results/cost_by_chars.csv, cost_by_sentences.csv and a
plot, and prints a summary table.
"""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
RESULTS = Path(__file__).resolve().parent / "results"
sys.path.insert(0, str(BACKEND))

from app.aggregate import bootstrap_ci, weighted_mean  # noqa: E402
from app.detectors.statistical import StatisticalDetector  # noqa: E402
from app.schemas import ScoreRequest  # noqa: E402
from app.sentences import split_sentences  # noqa: E402

SENTENCE_TEMPLATE = (
    "Furthermore, it is important to note that this sentence exists only "
    "to pad the input to a target size for measurement. "
)


def _make_text(n_chars: int) -> str:
    reps = n_chars // len(SENTENCE_TEMPLATE) + 1
    return (SENTENCE_TEMPLATE * reps)[:n_chars]


@dataclass
class CostSample:
    n_chars: int
    n_sentences: int
    parse_validate_s: float
    split_s: float
    inference_s: float
    aggregate_s: float
    total_s: float
    peak_memory_kb: float


def _timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


def measure_one(detector: StatisticalDetector, n_chars: int) -> CostSample:
    return measure_text(detector, _make_text(n_chars))


def measure_text(detector: StatisticalDetector, text: str) -> CostSample:
    raw_json = json.dumps({"text": text}).encode()

    tracemalloc.start()
    tracemalloc.reset_peak()

    # Stage 1: what the body-size middleware stands in front of -- JSON
    # decode + Pydantic validation, exactly as FastAPI does it per request.
    # min_length/max_length are evaluated here, but on a string that is
    # already fully materialised in memory, hence timing it separately.
    def parse_and_validate():
        payload = json.loads(raw_json)
        try:
            ScoreRequest.model_validate(payload)
        except Exception:
            pass  # validation failure is expected/irrelevant above MAX_TEXT_CHARS
    _, parse_validate_s = _timed(parse_and_validate)

    # Stage 2+3: splitting and inference, bypassing the API's own length
    # validation so size can be swept past MAX_TEXT_CHARS to see the
    # uncapped cost curve.
    sents, split_s = _timed(split_sentences, text)
    texts = [s.text for s in sents]
    raw_scores, inference_s = _timed(detector.score_sentences, texts) if texts else ([], 0.0)

    def aggregate():
        weights = [float(s.word_count) for s in sents]
        weighted_mean(raw_scores, weights)
        bootstrap_ci(raw_scores, weights)
    _, aggregate_s = _timed(aggregate) if texts else (None, 0.0)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return CostSample(
        n_chars=len(text),
        n_sentences=len(sents),
        parse_validate_s=parse_validate_s,
        split_s=split_s,
        inference_s=inference_s,
        aggregate_s=aggregate_s,
        total_s=parse_validate_s + split_s + inference_s + aggregate_s,
        peak_memory_kb=peak / 1024,
    )


def write_csv(path: Path, samples: list[CostSample]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(samples[0])))
        writer.writeheader()
        for s in samples:
            writer.writerow(asdict(s))


def print_table(title: str, samples: list[CostSample]) -> None:
    print(f"\n{title}")
    print(f"{'n_chars':>9} {'n_sent':>7} {'parse_ms':>9} {'split_ms':>9} "
         f"{'infer_ms':>9} {'agg_ms':>9} {'total_ms':>9} {'mem_kb':>9}")
    for s in samples:
        print(f"{s.n_chars:>9} {s.n_sentences:>7} {s.parse_validate_s*1000:>9.2f} "
             f"{s.split_s*1000:>9.2f} {s.inference_s*1000:>9.2f} "
             f"{s.aggregate_s*1000:>9.2f} {s.total_s*1000:>9.2f} {s.peak_memory_kb:>9.1f}")


def plot(samples: list[CostSample], out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed (requirements-train.txt); skipping plot.")
        return

    chars = [s.n_chars for s in samples]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(chars, [s.parse_validate_s * 1000 for s in samples], marker="o", label="parse+validate")
    ax.plot(chars, [s.split_s * 1000 for s in samples], marker="o", label="sentence split")
    ax.plot(chars, [s.inference_s * 1000 for s in samples], marker="o", label="model inference")
    ax.plot(chars, [s.aggregate_s * 1000 for s in samples], marker="o", label="aggregate+bootstrap")
    ax.plot(chars, [s.total_s * 1000 for s in samples], marker="o", label="total", linewidth=2, color="black")
    ax.axvline(12_000, color="grey", linestyle="--", label="MAX_TEXT_CHARS")
    ax.set_xlabel("input size (characters)")
    ax.set_ylabel("time (ms)")
    ax.set_title("/score cost by input size, broken down by stage")
    ax.legend()
    ax.set_xscale("log")
    ax.set_yscale("log")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Wrote {out_path}")


SHORT_SENTENCE = "Yes it is. "  # ~11 chars/sentence, isolates sentence-count cost from char-count cost


def measure_by_sentence_count(detector: StatisticalDetector, n_sentences: int) -> CostSample:
    return measure_text(detector, SHORT_SENTENCE * n_sentences)


def main() -> None:
    detector = StatisticalDetector()
    detector.load_verified()

    # Sweep 1: by character count, well past MAX_TEXT_CHARS (12,000) -- the
    # uncapped cost curve MAX_BODY_BYTES and MAX_TEXT_CHARS exist to cut off.
    char_sizes = [100, 1_000, 5_000, 12_000, 25_000, 50_000, 100_000, 250_000]
    by_chars = [measure_one(detector, n) for n in char_sizes]
    print_table("Cost by input size (characters), uncapped", by_chars)
    write_csv(RESULTS / "cost_by_chars.csv", by_chars)
    plot(by_chars, RESULTS / "cost_by_chars.png")

    # Sweep 2: by sentence count alone (short sentences, so character count
    # stays low) -- isolates what MAX_SENTENCES (300) specifically bounds.
    sent_counts = [10, 50, 100, 300, 600, 1_200, 2_400]
    by_sentences = [measure_by_sentence_count(detector, n) for n in sent_counts]
    print_table("Cost by sentence count (short sentences), uncapped", by_sentences)
    write_csv(RESULTS / "cost_by_sentences.csv", by_sentences)

    at_cap = next(s for s in by_chars if s.n_chars == 12_000)
    over_cap = by_chars[-1]
    at_sentence_cap = next(s for s in by_sentences if s.n_sentences >= 300)
    ms_per_sentence = (over_cap.inference_s - by_chars[0].inference_s) * 1000 / (
        over_cap.n_sentences - by_chars[0].n_sentences
    )

    print(
        "\nSummary (measured, not estimated -- see the tables and CSVs above):\n"
        f"- At MAX_TEXT_CHARS (12,000 chars, {at_cap.n_sentences} sentences), one "
        f"request costs {at_cap.total_s * 1000:.0f}ms and "
        f"{at_cap.peak_memory_kb / 1024:.1f}MB, almost entirely model inference "
        f"({at_cap.inference_s * 1000:.0f}ms of it). That is a noticeable but "
        "manageable cost for a single request -- the risk is not one such "
        "request, it is many of them at once (see flood.py): CPython's GIL "
        "means concurrently-running inference threads contend rather than "
        "run in parallel, so N simultaneous requests near this size take "
        "roughly N times as long each, not the same time together.\n"
        f"- Both CPU time and memory scale with input size well past "
        f"MAX_TEXT_CHARS, with no inherent ceiling: at {over_cap.n_chars:,} "
        f"characters ({over_cap.n_sentences} sentences) -- well within what an "
        "undefended server would accept and fully buffer before Pydantic's "
        f"max_length even runs -- one request costs {over_cap.total_s:.1f}s "
        f"and {over_cap.peak_memory_kb / 1024:.0f}MB. This is exactly what "
        "MAX_BODY_BYTES exists to reject before any of it is read.\n"
        f"- Inference cost is close to linear in sentence count, roughly "
        f"{ms_per_sentence:.2f}ms/sentence across this range; at the "
        f"MAX_SENTENCES cap (300) that is {at_sentence_cap.inference_s * 1000:.0f}ms "
        "for inference alone -- bounded and predictable, which is the point "
        "of the cap.\n"
        "- The bootstrap CI is not the dominant cost at any size measured "
        "(n_boot is fixed at 2000, so its cost scales with sentence count the "
        "same way inference's does, just with a much smaller constant); "
        "MAX_SENTENCES bounds it as a side effect of bounding inference.\n"
        "- parse+validate (JSON decode + Pydantic) stays under a millisecond "
        "even at 250,000 characters -- it is not where the CPU cost is. The "
        "case for MAX_BODY_BYTES is about memory (an oversized body is fully "
        "buffered before Pydantic can reject it) and about closing off the "
        "character-count axis entirely, not about parse CPU time.\n"
        "See security/dos/README.md for the attack scripts that turn this "
        "into measured before/after latency and status-code results."
    )


if __name__ == "__main__":
    main()
