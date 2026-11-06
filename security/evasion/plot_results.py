#!/usr/bin/env python3
"""Plots security/evasion/results/experiment.json (written by
run_experiment.py) as a grouped bar chart: evasion success rate per
technique and rate, undefended vs defended. Purely a visualisation of
numbers already measured and committed — run run_experiment.py first.

Usage (from the repository root):
    python security/evasion/plot_results.py
Writes security/evasion/results/evasion_rates.png.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RESULTS = Path(__file__).resolve().parent / "results"
TECHNIQUES = ["homoglyph", "invisible", "fullwidth", "combining", "mixed"]
RATES = [0.10, 0.25, 0.50]


def main() -> None:
    data = json.loads((RESULTS / "experiment.json").read_text())
    conditions = data["conditions"]

    fig, axes = plt.subplots(1, len(RATES), figsize=(13, 4.2), sharey=True)
    x = np.arange(len(TECHNIQUES))
    width = 0.35

    for ax, rate in zip(axes, RATES):
        undefended = []
        defended = []
        ci_u = []
        ci_d = []
        for t in TECHNIQUES:
            c = conditions[f"{t}_{int(rate * 100)}pct"]
            undefended.append(c["undefended"]["rate"] * 100)
            defended.append(c["defended"]["rate"] * 100)
            ci_u.append((c["undefended"]["rate"] - c["undefended"]["ci95"][0]) * 100)
            ci_d.append((c["defended"]["rate"] - c["defended"]["ci95"][0]) * 100)

        ax.bar(x - width / 2, undefended, width, yerr=ci_u, capsize=3,
               label="Undefended", color="#c0392b")
        ax.bar(x + width / 2, defended, width, yerr=ci_d, capsize=3,
               label="Defended", color="#2471a3")
        ax.set_title(f"{int(rate * 100)}% perturbation rate")
        ax.set_xticks(x)
        ax.set_xticklabels(TECHNIQUES, rotation=30, ha="right")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Evasion success rate (%)")
    axes[0].legend(loc="upper left")
    fig.suptitle("Detection-evasion success by technique and rate "
                 "(1,000 trials/condition; error bars = 95% bootstrap CI)")
    fig.tight_layout()
    out_path = RESULTS / "evasion_rates.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
