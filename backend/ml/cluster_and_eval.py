import pandas as pd
import sys
import matplotlib.pyplot as plt
import numpy as np
import joblib

from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.detectors.features import StylometricFeatures
from ml.train import (DEFAULT_DATASET, MAX_SENTS_PER_DOC, TRAIN_CAP_PER_CELL,
                      build_heldout_datasets, evaluate, load_dataset, make_pipeline,
                      model_zoo, sample_sentences, split_documents)
import json

# CLUSTERING PART
# --- Step 1: Load data and filter to AI-generated essays only ---
df = pd.read_csv(DEFAULT_DATASET)
ai_df = df[df["label"] == 1].copy()
print(f"AI-generated essays: {ai_df.shape[0]}")


# --- Step 2: Extract stylometric features ---
# ensuring clustering and classification are based on identical features.
features = StylometricFeatures()
X = features.transform(ai_df["text"])
feature_names = StylometricFeatures.FEATURE_NAMES


# --- Step 3: Scale features ---
# K-Means is distance-based, so features must be scaled to comparable
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)


# --- Step 4: Choose K using the Elbow Method ---
inertias = []
k_values = range(2, 9)

for k in k_values:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(X_scaled)
    inertias.append(km.inertia_)

plt.plot(list(k_values), inertias, marker="o")
plt.xlabel("Number of clusters (K)")
plt.ylabel("Inertia")
plt.title("Elbow Method for Choosing K")
plt.savefig("elbow_plot.png")
plt.show()


# --- Step 5: Choose K using Silhouette Score ---
silhouette_scores = []
for k in k_values:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    score = silhouette_score(X_scaled, labels, sample_size=5000, random_state=42)
    silhouette_scores.append(score)

print("Silhouette scores by K:", dict(zip(k_values, silhouette_scores)))


# --- Step 6: Final clustering ---
# K=6 chosen based on both methods:
# - Elbow plot: the inertia drop roughly halves after K=6 (about 20,000 to 12,000)
# - Among K=5,6,7 (the elbow's flat region), K=6 and K=7 tied for the
#   highest silhouette score (0.187), so K=6 was picked as the simpler option
final_k = 6
km_final = KMeans(n_clusters=final_k, random_state=42, n_init=10)
ai_df["cluster"] = km_final.fit_predict(X_scaled)
# Distance from each document to its own cluster centre (used to pick representative examples)
dist = km_final.transform(X_scaled)
ai_df["dist_to_centre"] = dist[np.arange(len(ai_df)), ai_df["cluster"].values]
print("\nCluster sizes:")
print(ai_df["cluster"].value_counts())

print(pd.crosstab(ai_df["cluster"], ai_df["source"]))
print(pd.crosstab(ai_df["cluster"], ai_df["source"], normalize="index").round(3))

# --- Step 7: Describe each cluster ---
# Compare each cluster's average feature values against the overall
# average to identify what makes each cluster distinct.
overall_avg = X.mean(axis=0)

for cluster_id in sorted(ai_df["cluster"].unique()):
    cluster_mask = ai_df["cluster"] == cluster_id
    cluster_avg = X[cluster_mask.values].mean(axis=0)
    diffs = cluster_avg - overall_avg

    print(f"\n--- Cluster {cluster_id} (n={cluster_mask.sum()}) ---")
    for name, diff, val in zip(feature_names, diffs, cluster_avg):
        print(f"{name}: cluster_avg={val:.3f}, diff_from_overall={diff:+.3f}")

    cluster_essays = ai_df[cluster_mask]
    dominant_source = cluster_essays["source"].value_counts().idxmax()

    # Use the document closest to the cluster centre as the most typical example,
    # skipping malformed rows that contain "Passage N:" placeholder text
    clean_essays = cluster_essays[~cluster_essays["text"].str.contains(r"Passage \d+:", regex=True, na=False)]
    example = clean_essays.nsmallest(1, "dist_to_centre")["text"].iloc[0]

    print(f"Dominant source: {dominant_source}")
    print(f"Example: {example[:300]}")

# --- Step 8: Data quality check ---
# Cross-checked Cluster 5 against source dataset: 1650/1652 essays (99.9%)
# originate from HC3, confirming clustering recovered a genuine stylistic
# difference between HC3 (short Q&A) and DAIGT (persuasive essays),
# rather than a data artifact.
print("\nCluster 5 source breakdown:")
print(ai_df[ai_df["cluster"] == 5]["source"].value_counts())

# Separately, found 6 DAIGT_v2 texts with malformed "Passage N:" placeholder text; these are skipped when picking examples.
suspicious = df[df["text"].str.contains(r"Passage \d+:", regex=True, na=False)]
print(f"\nMalformed rows found: {len(suspicious)} ({len(suspicious)/len(df)*100:.4f}%)")
print(suspicious["source"].value_counts())



    #EVALUATION PART
# --- Earlier tests with the old HC3-only model (results saved, kept for reference) ---
# v1: full DAIGT essays      -> holdout_daigt_full_hc3model.json
# v2: DAIGT sentences        -> holdout_daigt_sentences_hc3model.json

# --- Held-out generator family test ---
# The final model's configuration (TF-IDF + stylometric + discourse features,
# logistic regression, from ml/train.py) is trained twice on the same training split:
#   seen:   every AI generator family included
#   unseen: every AI document of HELDOUT_FAMILY removed
# Both are scored on the same test set: human sentences plus sentences from the
# held-out family, balanced 50/50. The drop from seen to unseen shows how much the
# detector relies on having seen that generator.
HELDOUT_FAMILY = "mistral"   # avoid "gpt": it covers every HC3 AI answer

full_df = load_dataset(DEFAULT_DATASET)
print("\nAI documents per source and family:")
print(full_df[full_df["label"] == 1].groupby(["source", "generator_family"]).size())


def fit_and_score(train, test):
    """Train the final model's configuration and score it on the test set."""
    pipe = make_pipeline(model_zoo()["logreg"])
    pipe.fit(train["text"].tolist(), train["label"].to_numpy())
    probs = pipe.predict_proba(test["text"].tolist())[:, 1]
    return probs, evaluate(test["label"], probs)


heldout = build_heldout_datasets(full_df, HELDOUT_FAMILY)
test = heldout["test"]
train_docs, _ = split_documents(full_df)
train_seen = sample_sentences(train_docs, TRAIN_CAP_PER_CELL, MAX_SENTS_PER_DOC)

print(f"\nTest sentences: {len(test)}")
_, m_seen = fit_and_score(train_seen, test)
probs, m_unseen = fit_and_score(heldout["train"], test)
print(f"Family seen in training:     {m_seen}")
print(f"Family held out of training: {m_unseen}")

with open(f"heldout_family_{HELDOUT_FAMILY}.json", "w") as f:
    json.dump({"heldout_family": HELDOUT_FAMILY, "seen": m_seen, "unseen": m_unseen}, f, indent=2)

# --- Error analysis: misclassified sentences from the held-out model ---
pred = (probs >= 0.5).astype(int)
y = test["label"].to_numpy()
rng = np.random.default_rng(42)
for title, mask in (("FALSE POSITIVES (human predicted as AI)", (y == 0) & (pred == 1)),
                    ("FALSE NEGATIVES (AI predicted as human)", (y == 1) & (pred == 0))):
    rows = test[mask]
    print(f"\n=== {title}: {len(rows)} ===")
    for i in rng.choice(len(rows), size=min(8, len(rows)), replace=False):
        r = rows.iloc[i]
        print(f"[{r['source']} / {r['generator']}] {r['text']}\n---")