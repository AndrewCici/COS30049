"""Train the statistical detector (Stage 2).

Dataset: HC3 (Hello-SimpleAI) — pairs of human and ChatGPT answers to the
same questions (Reddit ELI5, finance, medicine, open QA, wiki CS/AI).
Chosen because it is public, balanced by construction, and matches the
product's unit of analysis after sentence-splitting.

Key methodology decisions:
- The train/test split is grouped by *question*, so no answer to a test
  question (human or AI) is ever seen in training — prevents topic leakage
  inflating the metrics.
- Training examples are *sentences*, not documents, because the product
  scores sentences. Sentences with fewer than 5 words are dropped (too
  little signal; the UI warns about short text separately).
- Classifier: logistic regression over word/char TF-IDF + stylometric
  features. Linear models on n-grams are a strong, fast, interpretable
  baseline, and their probability outputs are reasonably well calibrated —
  which matters because the UI presents scores as probabilities.

Usage:
    python -m ml.train            # downloads HC3, trains, evaluates, saves
"""
import json
import random
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.detectors.features import StylometricFeatures  # noqa: E402
from app.sentences import split_sentences  # noqa: E402

MODELS = BACKEND / "models"
DATA = BACKEND / "ml" / "data"
SEED = 42
MIN_WORDS, MAX_WORDS = 5, 120
TRAIN_CAP_PER_CLASS = 40_000
TEST_CAP_PER_CLASS = 8_000


def load_hc3() -> list[dict]:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(
        repo_id="Hello-SimpleAI/HC3", repo_type="dataset", filename="all.jsonl"
    )
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def to_sentences(answers: list[str]) -> list[str]:
    out = []
    for ans in answers or []:
        for s in split_sentences(ans):
            if MIN_WORDS <= s.word_count <= MAX_WORDS:
                out.append(s.text)
    return out


def build_splits(records: list[dict]):
    rng = random.Random(SEED)
    train = {"text": [], "label": []}
    test = {"text": [], "label": []}
    for rec in records:
        bucket = train if rng.random() < 0.8 else test  # grouped by question
        for label, key in ((0, "human_answers"), (1, "chatgpt_answers")):
            for sent in to_sentences(rec.get(key)):
                bucket["text"].append(sent)
                bucket["label"].append(label)

    def cap(split, cap_per_class):
        idx_by_class = {0: [], 1: []}
        for i, y in enumerate(split["label"]):
            idx_by_class[y].append(i)
        keep = []
        for y, idxs in idx_by_class.items():
            rng.shuffle(idxs)
            keep.extend(idxs[:cap_per_class])
        rng.shuffle(keep)
        return ([split["text"][i] for i in keep], [split["label"][i] for i in keep])

    return cap(train, TRAIN_CAP_PER_CLASS), cap(test, TEST_CAP_PER_CLASS)


def build_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    features = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(
            ngram_range=(1, 2), max_features=100_000, min_df=3,
            sublinear_tf=True, lowercase=True)),
        ("char_tfidf", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), max_features=100_000,
            min_df=3, sublinear_tf=True, lowercase=True)),
        ("stylometric", StylometricFeatures()),
    ])
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(C=1.0, max_iter=2000, solver="liblinear")),
    ])


def evaluate(y_true, y_prob) -> dict:
    import numpy as np
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 confusion_matrix, f1_score,
                                 precision_score, recall_score,
                                 roc_auc_score)
    y_pred = (np.asarray(y_prob) >= 0.5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_ai": round(float(precision_score(y_true, y_pred)), 4),
        "recall_ai": round(float(recall_score(y_true, y_pred)), 4),
        "f1_ai": round(float(f1_score(y_true, y_pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "n_test": int(len(y_true)),
    }


def main():
    import joblib

    MODELS.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)

    print("Loading HC3…")
    records = load_hc3()
    print(f"  {len(records)} question records")

    (X_train, y_train), (X_test, y_test) = build_splits(records)
    print(f"  train sentences: {len(X_train)}  test sentences: {len(X_test)}")

    # Persist the test split so other detectors (the HF transformer) can be
    # evaluated on exactly the same data.
    with open(DATA / "test_split.jsonl", "w") as f:
        for t, y in zip(X_test, y_test):
            f.write(json.dumps({"text": t, "label": y}) + "\n")

    print("Training…")
    pipe = build_pipeline()
    pipe.fit(X_train, y_train)

    print("Evaluating…")
    y_prob = pipe.predict_proba(X_test)[:, 1]
    metrics = evaluate(y_test, y_prob)
    print(json.dumps(metrics, indent=2))

    version = f"{date.today().isoformat()}-hc3"
    joblib.dump(pipe, MODELS / "statistical_model.joblib", compress=3)
    (MODELS / "statistical_model.meta.json").write_text(json.dumps({
        "model_name": "tfidf-stylometric-logreg",
        "version": version,
        "dataset": "Hello-SimpleAI/HC3 (all.jsonl), sentence-level, "
                   "question-grouped 80/20 split",
        "train_sentences": len(X_train),
        "test_sentences": len(X_test),
        "metrics": metrics,
    }, indent=2))
    print(f"Saved model + meta to {MODELS}")


if __name__ == "__main__":
    main()
