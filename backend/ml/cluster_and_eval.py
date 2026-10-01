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
from ml.train import evaluate

# CLUSTERING PART
# --- Step 1: Load data and filter to AI-generated essays only ---
df = pd.read_csv("data/merged_dataset.csv")
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
# - Elbow plot shows inertia improvement flattening from K~5 onward
# - Among K=5,6,7 (the elbow's flat region), K=6 and K=7 tied for the
#   highest silhouette score (0.187), so K=6 was picked as the simpler option
final_k = 6
km_final = KMeans(n_clusters=final_k, random_state=42, n_init=10)
ai_df["cluster"] = km_final.fit_predict(X_scaled)

print("\nCluster sizes:")
print(ai_df["cluster"].value_counts())


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

    # Prefer an example from the cluster's dominant source, when available,
    dominant_source = cluster_essays["source"].value_counts().idxmax()
    source_essays = cluster_essays[cluster_essays["source"] == dominant_source]

    clean_essays = source_essays[~source_essays["text"].str.contains(r"Passage \d+:", regex=True, na=False)]
    example = clean_essays["text"].iloc[0] if len(clean_essays) > 0 else cluster_essays["text"].iloc[0]

    print(f"Dominant source: {dominant_source}")
    print(f"Example: {example[:300]}")


# --- Step 8: Data quality check ---
# Cross-checked Cluster 5 against source dataset: 1650/1652 essays (99.9%)
# originate from HC3, confirming clustering recovered a genuine stylistic
# difference between HC3 (short Q&A) and DAIGT (persuasive essays),
# rather than a data artifact.
print("\nCluster 5 source breakdown:")
print(ai_df[ai_df["cluster"] == 5]["source"].value_counts())

# Separately, found 6/586,217 rows (0.001%) with malformed "Passage N:" placeholder text, all from DAIGT_v2.
suspicious = df[df["text"].str.contains(r"Passage \d+:", regex=True, na=False)]
print(f"\nMalformed rows found: {len(suspicious)} ({len(suspicious)/len(df)*100:.4f}%)")
print(suspicious["source"].value_counts())


#EVALUATION PART
#  Load trained classifier for evaluation
MODELS_DIR = BACKEND / "models"
model = joblib.load(MODELS_DIR / "statistical_model.joblib")
print("\nModel loaded successfully")

print(df["source"].value_counts())
print(df[df["source"] == "DAIGT_v2"]["label"].value_counts())

# --- Held-out test v1: entire DAIGT_v2 (model trained on HC3-only) ---
held_out_df = df[df["source"] == "DAIGT_v2"]
y_prob = model.predict_proba(held_out_df["text"])[:, 1]
metrics_v1 = evaluate(held_out_df["label"], y_prob)

# --- Held-out test v2: single topic (model trained on merged dataset) ---
# held_out_df = df[df["topic"] == "Phones and driving"]
# y_prob = model.predict_proba(held_out_df["text"])[:, 1]
# metrics_v2 = evaluate(held_out_df["label"], y_prob)

#Error Analysis
y_pred = (y_prob >= 0.5).astype(int)

fp_mask = (held_out_df["label"].values == 0) & (y_pred == 1)  # human bị đoán nhầm AI
fn_mask = (held_out_df["label"].values == 1) & (y_pred == 0)  # AI bị đoán nhầm human

false_positives = held_out_df[fp_mask]
false_negatives = held_out_df[fn_mask]

print("False positives:", len(false_positives))
print("False negatives:", len(false_negatives))


# --- Error analysis: inspect false positives and false negatives from the held-out test ---
# False negatives (AI misclassified as human)
print("=== FALSE NEGATIVES ===")
for text in false_negatives["text"]:
    print(text[:300])
    print("---")

# False positives (human misclassified as AI) — random sample of 5
print("\n=== FALSE POSITIVES (sample of 5) ===")
for text in false_positives["text"].sample(5, random_state=42):
    print(text[:300])
    print("---")