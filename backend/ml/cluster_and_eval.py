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
from ml.train import evaluate, to_sentences
import json

# CLUSTERING PART
# --- Step 1: Load data and filter to AI-generated essays only ---
df = pd.read_csv("data/merged_dataset._v2.csv")
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
#Inspoect 5 documents xlosest to cluster 4 and get example
    for t in ai_df[ai_df["cluster"] == 4].nsmallest(5, "dist_to_centre")["text"]:
        print(t[:300])
        print("---")

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
# Load trained classifier for evaluation
MODELS_DIR = BACKEND / "models"
model = joblib.load(MODELS_DIR / "statistical_model.joblib")
print("\nModel loaded successfully")

# --- Generalisation test v1: full DAIGT essays (already run) ---
# The HC3-trained model scored full DAIGT_v2 essays. Result saved in
# holdout_daigt_full_hc3model.json, kept here for reference only.
# held_out_df = df[df["source"] == "DAIGT_v2"]
# y_prob = model.predict_proba(held_out_df["text"])[:, 1]
# metrics_v1 = evaluate(held_out_df["label"], y_prob)

# --- Generalisation test v2: DAIGT sentences ---
# The model was trained on sentences, so DAIGT_v2 essays are split the same way
# (5-120 words per sentence) and each sentence inherits its essay's label.
# A random sample of 10,000 essays keeps the run time manageable.
held_out_df = df[df["source"] == "DAIGT_v2"].sample(10000, random_state=42)

sent_texts, sent_labels = [], []
for text, label in zip(held_out_df["text"], held_out_df["label"]):
    for s in to_sentences([text]):
        sent_texts.append(s)
        sent_labels.append(int(label))

print(f"DAIGT sentences: {len(sent_texts)}")
y_prob_sent = model.predict_proba(sent_texts)[:, 1]
metrics_v2 = evaluate(sent_labels, y_prob_sent)
print(metrics_v2)

with open("holdout_daigt_sentences_hc3model.json", "w") as f:
    json.dump(metrics_v2, f, indent=2)

# --- Generalisation test v3 (only if a model trained on merged data is provided) ---
# Use the topic that was left out of training, split into sentences as above.
# held_out_df = df[df["topic"] == "Phones and driving"]

# --- Error analysis: misclassified sentences from test v2 ---
y_pred_sent = (y_prob_sent >= 0.5).astype(int)
labels_arr = np.array(sent_labels)
texts_arr = np.array(sent_texts, dtype=object)

false_positives = texts_arr[(labels_arr == 0) & (y_pred_sent == 1)]  # human predicted as AI
false_negatives = texts_arr[(labels_arr == 1) & (y_pred_sent == 0)]  # AI predicted as human
print(f"\nFalse positives: {len(false_positives)}")
print(f"False negatives: {len(false_negatives)}")

# Random samples of each error type for manual inspection
rng = np.random.default_rng(42)
print("\n=== FALSE POSITIVES (sample of 8) ===")
for t in rng.choice(false_positives, size=min(8, len(false_positives)), replace=False):
    print(t)
    print("---")

print("\n=== FALSE NEGATIVES (sample of 8) ===")
for t in rng.choice(false_negatives, size=min(8, len(false_negatives)), replace=False):
    print(t)
    print("---")