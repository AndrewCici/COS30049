#!/usr/bin/env python3
"""Attack 1: one "expensive" request, shaped two different ways, while
polling /health every 100ms to see whether the server stays responsive.

Both payloads stay within what a naive read of "input limits" might expect
to be fine, which is the point -- they rely on what an undefended server
accepts, not on brute size alone (see measure_cost.py):

- sentence-flood: ~3,000 one-word "sentences" packed into ~12,000
  characters (under MAX_TEXT_CHARS, so Pydantic's length check alone never
  stops it) -- this is what MAX_SENTENCES exists to reject.
- oversized-body: a body far past MAX_BODY_BYTES (64 KiB) but still under
  MAX_TEXT_CHARS once (if ever) fully parsed -- this is what the body-size
  middleware exists to reject before it is ever read.

Usage:
    python security/dos/expensive_request.py --base-url http://localhost:8000 \\
        --scenario sentence-flood --label defences_on
    python security/dos/expensive_request.py --scenario oversized-body --label defences_off

Requires a running backend (see security/dos/README.md for how to start one
with SECURITY_DEFENCES=on/off). Writes a CSV latency timeline and a PNG
plot to security/dos/results/.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

RESULTS = Path(__file__).resolve().parent / "results"

SCENARIOS = {
    "sentence-flood": lambda: "Hi. " * 3_000,          # ~12,000 chars, ~3,000 sentences
    "oversized-body": lambda: "word " * 4_000_000,     # ~20MB, far past MAX_BODY_BYTES and MAX_TEXT_CHARS
}


@dataclass
class HealthPoll:
    t_s: float
    status: int | None
    latency_ms: float


async def poll_health(base_url: str, stop: asyncio.Event, out: list[HealthPoll], t0: float) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        while not stop.is_set():
            poll_t0 = time.perf_counter()
            try:
                r = await client.get(f"{base_url}/api/v1/health")
                status = r.status_code
            except httpx.HTTPError:
                status = None
            latency_ms = (time.perf_counter() - poll_t0) * 1000
            out.append(HealthPoll(t_s=poll_t0 - t0, status=status, latency_ms=latency_ms))
            await asyncio.sleep(0.1)


async def run(base_url: str, scenario: str) -> tuple[list[HealthPoll], dict]:
    text = SCENARIOS[scenario]()
    t0 = time.perf_counter()
    polls: list[HealthPoll] = []
    stop = asyncio.Event()
    poller = asyncio.create_task(poll_health(base_url, stop, polls, t0))

    result = {"scenario": scenario, "n_chars": len(text)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        req_t0 = time.perf_counter()
        try:
            r = await client.post(f"{base_url}/api/v1/score", json={"text": text})
            result["status"] = r.status_code
            result["error_code"] = (r.json().get("error", {}).get("code")
                                    if r.status_code >= 400 else None)
        except httpx.HTTPError as exc:
            result["status"] = None
            result["error_code"] = f"transport:{type(exc).__name__}"
        result["request_latency_ms"] = (time.perf_counter() - req_t0) * 1000

    await asyncio.sleep(0.3)  # a few more health polls after the request finishes
    stop.set()
    await poller
    return polls, result


def write_csv(path: Path, polls: list[HealthPoll]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["t_s", "status", "latency_ms"])
        for p in polls:
            writer.writerow([f"{p.t_s:.3f}", p.status, f"{p.latency_ms:.2f}"])


def plot(polls: list[HealthPoll], result: dict, out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot.")
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    t = [p.t_s for p in polls]
    lat = [p.latency_ms for p in polls]
    colors = ["#2a9d2a" if p.status == 200 else "#c0392b" for p in polls]
    ax.scatter(t, lat, c=colors, s=18)
    ax.axvline(0, color="grey", linestyle="--", linewidth=1, label="/score sent")
    req_end_s = (result["request_latency_ms"] / 1000)
    ax.axvline(req_end_s, color="black", linestyle=":", linewidth=1, label="/score finished")
    ax.set_xlabel("time since /score was sent (s)")
    ax.set_ylabel("/health latency (ms)")
    ax.set_title(f"/health latency while one '{result['scenario']}' request is in flight\n"
                f"(/score -> {result['status']} in {result['request_latency_ms']:.0f}ms; "
                "green=200, red=non-200/error)")
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Wrote {out_path}")


async def main_async(args: argparse.Namespace) -> None:
    polls, result = await run(args.base_url, args.scenario)
    print(f"Scenario: {result['scenario']} ({result['n_chars']:,} chars)")
    print(f"/score -> status={result['status']} error_code={result['error_code']} "
         f"latency={result['request_latency_ms']:.1f}ms")
    non200 = [p for p in polls if p.status != 200]
    print(f"/health polls: {len(polls)} total, {len(non200)} non-200/failed")
    if polls:
        print(f"/health latency: min={min(p.latency_ms for p in polls):.1f}ms "
             f"max={max(p.latency_ms for p in polls):.1f}ms")

    stem = f"expensive_request_{args.scenario.replace('-', '_')}_{args.label}"
    write_csv(RESULTS / f"{stem}.csv", polls)
    plot(polls, result, RESULTS / f"{stem}.png")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--scenario", choices=list(SCENARIOS), required=True)
    ap.add_argument("--label", default="run", help="suffix for output filenames, "
                    "e.g. defences_on / defences_off")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
