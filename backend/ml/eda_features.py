"""EDA: how each stylometric and discourse feature differs between human and AI text."""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.detectors.features import DiscourseFeatures, StylometricFeatures  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else "data/merged_dataset_v2.csv"
df = pd.read_csv(DATA).dropna(subset=["text"])
df = pd.concat([g.sample(min(len(g), 10000), random_state=42) for _, g in df.groupby("label")])

texts = df["text"].tolist()
X = np.hstack([StylometricFeatures().transform(texts), DiscourseFeatures().transform(texts)])
names = list(StylometricFeatures.FEATURE_NAMES) + list(DiscourseFeatures.FEATURE_NAMES)
feats = pd.DataFrame(X, columns=names)
y = df["label"].to_numpy()

# Standardised mean difference (AI minus human), so features on different scales can be compared
h, a = feats[y == 0], feats[y == 1]
pooled = np.sqrt((h.var() + a.var()) / 2).replace(0, np.nan)
smd = ((a.mean() - h.mean()) / pooled).sort_values()

colours = ["#c0504d" if v > 0 else "#4f81bd" for v in smd]
fig, ax = plt.subplots(figsize=(8, 7))
ax.barh(smd.index, smd.values, color=colours)
ax.axvline(0, color="black", linewidth=0.8)
ax.set_xlabel("Standardised mean difference (AI − human)")
ax.set_title("Feature differences between AI and human text")
fig.tight_layout()
fig.savefig("eda_feature_differences.png", dpi=200)

summary = pd.DataFrame({"human_mean": h.mean(), "ai_mean": a.mean(), "smd": smd}).sort_values("smd")
summary.round(3).to_csv("eda_feature_summary.csv")
print(summary.round(3))