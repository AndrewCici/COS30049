#!/usr/bin/env python3
"""Attack 2: N concurrent /score requests at once, all a legitimate size
(well within MAX_TEXT_CHARS / MAX_SENTENCES -- this is not about an
oversized payload, it is about volume). Records the status code of every
response and latency percentiles.

With the concurrency limiter on, most requests beyond its capacity
(MAX_CONCURRENT_INFERENCES + MAX_QUEUED) should fail fast with 503 instead
of queuing indefinitely, and the ones that do run should stay close to their
solo latency. With it off, expect far more 200s but with latency growing
with N, since CPython's GIL serialises the CPU-bound inference work across
however many threads are actually running it.

Usage:
    python security/dos/flood.py --base-url http://localhost:8000 -n 200 --label defences_on
    python security/dos/flood.py -n 200 --label defences_off

Requires a running backend. Writes a CSV of every response and a PNG plot
to security/dos/results/.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

RESULTS = Path(__file__).resolve().parent / "results"

# Just under MAX_TEXT_CHARS (12,000), ~100 real sentences -- the same shape
# as a legitimate maximal request in measure_cost.py (~130ms of
# server-side work each).
TEXT = ((
    "Furthermore, it is important to note that this sentence exists only "
    "to pad the input to a realistic size for the flood test. "
) * 100)[:11_999]


@dataclass
class Result:
    i: int
    status: int | None
    error_code: str | None
    retry_after: str | None
    latency_ms: float


async def one_request(client: httpx.AsyncClient, base_url: str, i: int) -> Result:
    t0 = time.perf_counter()
    try:
        r = await client.post(f"{base_url}/api/v1/score", json={"text": TEXT})
        status = r.status_code
        error_code = r.json().get("error", {}).get("code") if status >= 400 else None
        retry_after = r.headers.get("retry-after")
    except httpx.HTTPError as exc:
        status, error_code, retry_after = None, f"transport:{type(exc).__name__}", None
    return Result(i=i, status=status, error_code=error_code, retry_after=retry_after,
                 latency_ms=(time.perf_counter() - t0) * 1000)


async def run(base_url: str, n: int) -> list[Result]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [one_request(client, base_url, i) for i in range(n)]
        return await asyncio.gather(*tasks)


def percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    s = sorted(values)

    def pct(p: float) -> float:
        idx = min(int(len(s) * p), len(s) - 1)
        return s[idx]
    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99)}


def write_csv(path: Path, results: list[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["i", "status", "error_code", "retry_after", "latency_ms"])
        for r in results:
            writer.writerow([r.i, r.status, r.error_code or "", r.retry_after or "",
                            f"{r.latency_ms:.2f}"])


def plot(results: list[Result], out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot.")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    counts: dict[str, int] = {}
    for r in results:
        key = str(r.status) if r.status else "no response"
        counts[key] = counts.get(key, 0) + 1
    ax1.bar(list(counts), list(counts.values()), color="#4472c4")
    ax1.set_title("Response status counts")
    ax1.set_ylabel("count")

    by_status: dict[str, list[float]] = {}
    for r in results:
        key = str(r.status) if r.status else "no response"
        by_status.setdefault(key, []).append(r.latency_ms)
    for key, lats in by_status.items():
        ax2.scatter([key] * len(lats), lats, alpha=0.5, s=14)
    ax2.set_title("Latency by status")
    ax2.set_ylabel("latency (ms)")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--label", default="run")
    args = ap.parse_args()

    results = asyncio.run(run(args.base_url, args.n))

    counts: dict[str, int] = {}
    for r in results:
        key = str(r.status) if r.status else "no response"
        counts[key] = counts.get(key, 0) + 1
    all_lat = [r.latency_ms for r in results]
    ok_lat = [r.latency_ms for r in results if r.status == 200]

    print(f"N={args.n} concurrent requests")
    print(f"Status counts: {counts}")
    print(f"Latency (all):  {percentiles(all_lat)}")
    print(f"Latency (200s): {percentiles(ok_lat)}" if ok_lat else "Latency (200s): none succeeded")
    if all_lat:
        print(f"mean={statistics.mean(all_lat):.1f}ms max={max(all_lat):.1f}ms")

    stem = f"flood_n{args.n}_{args.label}"
    write_csv(RESULTS / f"{stem}.csv", results)
    plot(results, RESULTS / f"{stem}.png")


if __name__ == "__main__":
    main()
