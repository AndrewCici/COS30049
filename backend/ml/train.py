"""Train and compare AI-text detectors (Assignment 2, Person A).

Goal: pick the model that keeps separating human from AI text on data it has
not seen, not the one with the best random-split accuracy. Every model is
scored in-distribution (sentence and essay level) and cross-source (train on
HC3 -> test on DAIGT, and the reverse). The final model is the one with the
highest mean cross-source ROC-AUC.

Usage (from backend/):
    python -m ml.train                  # full run
    python -m ml.train --fast           # ~10x smaller; writes to ml/_smoke/, never models/
    python -m ml.train --models logreg,xgboost --skip-cross
    python -m ml.evaluate_hf && python -m ml.train --table-only
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.detectors.features import DiscourseFeatures, StylometricFeatures  # noqa: E402
from app.sentences import split_sentences  # noqa: E402

MODELS = BACKEND / "models"
DATA = BACKEND / "ml" / "data"
CACHE = BACKEND / "ml" / ".cache"
DEFAULT_DATASET = BACKEND.parent / "dataprep" / "merged_dataset.csv"

SEED = 42
MIN_WORDS, MAX_WORDS = 5, 120
TEST_FRACTION = 0.2
MAX_SENTS_PER_DOC = 5
TRAIN_CAP_PER_CELL = 20_000   # sentences per (source, label) cell
TEST_CAP_PER_CELL = 4_000     # sentence-level test, per cell
TEST_DOCS_PER_CELL = 500      # documents kept for essay-level evaluation
SVM_TRAIN_CAP = 20_000        # RBF-SVM is O(n^2)-O(n^3); cap total train size

CELL = ["source", "label"]


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def load_dataset(path: Path | str = DEFAULT_DATASET) -> pd.DataFrame:
    """Load the merged dataset (or a raw DAIGT v2 file) into one schema.

    Output columns: text, label (0=human, 1=AI), source (dataset name),
    topic, group (split-unit id), generator (LLM name if known),
    generator_family (llama, mistral, ... ; defaults to `generator`).

    Same {"text", "label"} shape as the old load_hc3(), plus metadata.
    Two input layouts are accepted:
    - merged file from ml/data_prep: text,label,source,topic[,group,generator]
    - raw DAIGT v2 (train_v2_drcat_02.csv): has `prompt_name`; its `source`
      column is the *generator*, so it is renamed.
    """
    df = pd.read_csv(path)
    if "prompt_name" in df.columns:  # raw DAIGT v2
        df = df.rename(columns={"source": "generator", "prompt_name": "topic"})
        df["source"] = "DAIGT_v2"
    for col, default in (("topic", "unknown"), ("generator", "unknown")):
        if col not in df.columns:
            df[col] = default
    if "generator_family" not in df.columns:
        df["generator_family"] = df["generator"]
    df = df.dropna(subset=["text", "label"]).copy()
    df["text"] = df["text"].astype(str)
    df["label"] = df["label"].astype(int)
    # `group` = unit that must never straddle the train/test boundary. If the
    # file has no explicit group (e.g. HC3 question id), each row is its own.
    raw_group = df["group"].astype(str) if "group" in df.columns else df.index.astype(str)
    df["group"] = df["source"].astype(str) + ":" + raw_group
    return df[["text", "label", "source", "topic", "group", "generator",
               "generator_family"]].reset_index(drop=True)


def split_documents(df: pd.DataFrame, seed: int = SEED):
    """Grouped 80/20 split at document level (before sentence splitting)."""
    rng = np.random.RandomState(seed)
    groups = df["group"].unique()
    n_test = int(len(groups) * TEST_FRACTION)
    test_groups = set(rng.choice(groups, size=n_test, replace=False))
    is_test = df["group"].isin(test_groups)
    return df[~is_test], df[is_test]


def doc_sentences(text: str) -> list[tuple[str, int]]:
    """(sentence, word_count) pairs that pass the length filter."""
    return [(s.text, s.word_count) for s in split_sentences(text)
            if MIN_WORDS <= s.word_count <= MAX_WORDS]


def sample_sentences(docs: pd.DataFrame, cap_per_cell: int | None,
                     max_per_doc: int | None, seed: int = SEED) -> pd.DataFrame:
    """Turn documents into a sentence table, balanced per (source, label) cell.

    Documents are visited in random order; up to `max_per_doc` random
    sentences are taken from each until the cell reaches `cap_per_cell`.
    `cap_per_cell=None` keeps every sentence of every document (essay eval).
    """
    rng = np.random.RandomState(seed)
    rows = []
    for (source, label), cell in docs.groupby(CELL):
        texts, groups, gens = (cell["text"].to_numpy(), cell["group"].to_numpy(),
                               cell["generator"].to_numpy())
        taken = 0
        for i in rng.permutation(len(cell)):
            if cap_per_cell is not None and taken >= cap_per_cell:
                break
            sents = doc_sentences(texts[i])
            if max_per_doc is not None and len(sents) > max_per_doc:
                keep = np.sort(rng.choice(len(sents), max_per_doc, replace=False))
                sents = [sents[k] for k in keep]
            if cap_per_cell is not None:
                sents = sents[: cap_per_cell - taken]
            for text, wc in sents:
                rows.append((text, label, source, groups[i], gens[i], wc))
            taken += len(sents)
    return pd.DataFrame(rows, columns=["text", "label", "source", "doc_id", "generator", "w"])


def _cap_per_cell(df: pd.DataFrame, n: int, seed: int = SEED) -> pd.DataFrame:
    parts = [g.sample(min(len(g), n), random_state=seed) for _, g in df.groupby(CELL)]
    return pd.concat(parts).sort_index()


def build_datasets(df: pd.DataFrame, scale: float = 1.0) -> dict[str, pd.DataFrame]:
    """Return {'train', 'essay_test', 'sent_test'} sentence tables.

    sent_test is a subset of essay_test (flag `in_sent_test`), so each model
    only has to predict once.
    """
    train_docs, test_docs = split_documents(df)
    train = sample_sentences(train_docs, int(TRAIN_CAP_PER_CELL * scale), MAX_SENTS_PER_DOC)
    test_docs = _cap_per_cell(test_docs, max(int(TEST_DOCS_PER_CELL * scale), 20))
    essay = sample_sentences(test_docs, None, None)
    sent = _cap_per_cell(essay, max(int(TEST_CAP_PER_CELL * scale), 50))
    essay["in_sent_test"] = essay.index.isin(sent.index)
    return {"train": train, "essay_test": essay, "sent_test": essay[essay["in_sent_test"]]}


def build_heldout_datasets(df: pd.DataFrame, heldout_family: str,
                           scale: float = 1.0) -> dict[str, pd.DataFrame]:
    """Generalisation test: no AI text from `heldout_family` is seen in training.

    train = train-split documents minus every AI document of that family.
    test  = test-split human documents + test-split AI documents of that
            family only, rebalanced to 50/50 (so accuracy is interpretable).
    Returns {'train', 'test'} sentence tables (columns: text, label, source,
    doc_id, generator, w). Use `generator_family` values such as "mistral",
    "llama", "palm", "falcon". Avoid "gpt": it contains every HC3 AI answer,
    so holding it out leaves HC3 with human text only and the model can learn
    "HC3 style = human" as a shortcut.
    """
    train_docs, test_docs = split_documents(df)
    train_docs = train_docs[train_docs["generator_family"] != heldout_family]
    test_docs = test_docs[(test_docs["label"] == 0)
                          | (test_docs["generator_family"] == heldout_family)]
    if (test_docs["label"] == 1).sum() == 0:
        families = sorted(df.loc[df["label"] == 1, "generator_family"].unique())
        raise ValueError(f"no AI test documents for {heldout_family!r}; choose from {families}")
    train = sample_sentences(train_docs, int(TRAIN_CAP_PER_CELL * scale), MAX_SENTS_PER_DOC)
    if train.groupby(CELL).ngroups < 4:
        print(f"WARNING: training lacks a (source, label) cell after holding out "
              f"{heldout_family!r}; dataset identity may leak the label.", flush=True)
    test_docs = _cap_per_cell(test_docs, max(int(TEST_DOCS_PER_CELL * scale), 20))
    test = sample_sentences(test_docs, None, None)
    test = balanced_cap(test, 2 * int(test["label"].value_counts().min()))
    return {"train": train, "test": test.reset_index(drop=True)}


# --------------------------------------------------------------------------
# Features and models
# --------------------------------------------------------------------------
def sparse_features(max_features: int = 100_000):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion
    return FeatureUnion([
        ("word_tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=max_features, min_df=3,
                                       sublinear_tf=True, lowercase=True)),
        ("char_tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                       max_features=max_features, min_df=3,
                                       sublinear_tf=True, lowercase=True)),
        ("stylometric", StylometricFeatures()),
        ("discourse", DiscourseFeatures()),
    ])


def sparse_features_small():
    """20k+20k columns for XGBoost: histogram-based boosting allocates
    memory per feature, so 200k columns exhausts RAM on a laptop."""
    return sparse_features(max_features=20_000)


def dense_features():
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion, Pipeline
    return FeatureUnion([
        ("lexical_svd", Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=50_000, min_df=3,
                                      sublinear_tf=True)),
            ("svd", TruncatedSVD(n_components=100, random_state=SEED)),
        ])),
        ("stylometric", StylometricFeatures()),
        ("discourse", DiscourseFeatures()),
    ])


@dataclass
class Spec:
    label: str                       # name used in tables
    model_name: str                  # name stored in meta.json / API
    features: Callable               # sparse_features | dense_features
    scale: bool                      # StandardScaler before the classifier?
    kind: str                        # "unit" | "beyond-unit"
    make: Callable                   # () -> sklearn-compatible estimator
    train_cap: int | None = None     # optional cap on total training size


def model_zoo() -> dict[str, Spec]:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.svm import SVC
    from sklearn.tree import DecisionTreeClassifier

    def xgb():
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.1, subsample=0.8,
                             colsample_bytree=0.5, tree_method="hist", max_bin=64, n_jobs=-1,
                             random_state=SEED, eval_metric="logloss")

    # StandardScaler only for KNN and SVM (distance/margin based); trees ignore scale.
    # Dense view (SVD + stylometric) because KNN/SVM/RF cannot handle ~200k sparse columns.
    return {
        "logreg": Spec("Logistic Regression", "tfidf-stylometric-logreg", sparse_features, False,
                       "unit", lambda: LogisticRegression(C=1.0, max_iter=2000, solver="liblinear")),
        "knn": Spec("k-NN (k=25)", "svd-stylometric-knn", dense_features, True, "unit",
                    lambda: KNeighborsClassifier(n_neighbors=25, n_jobs=-1)),
        "decision_tree": Spec("Decision Tree", "svd-stylometric-decision-tree", dense_features,
                              False, "unit",
                              lambda: DecisionTreeClassifier(max_depth=12, min_samples_leaf=20,
                                                             random_state=SEED)),
        "random_forest": Spec("Random Forest", "svd-stylometric-random-forest", dense_features,
                              False, "unit",
                              lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                                             n_jobs=-1, random_state=SEED)),
        # SVC has no probabilities of its own; Platt-style sigmoid calibration on
        # held-out folds turns its margin into a probability (SVC(probability=True)
        # is deprecated in scikit-learn 1.9).
        "svm_rbf": Spec("SVM (RBF)", "svd-stylometric-svm-rbf", dense_features, True, "unit",
                        lambda: CalibratedClassifierCV(SVC(kernel="rbf", C=1.0, gamma="scale"),
                                                       method="sigmoid", cv=3, ensemble=False),
                        train_cap=SVM_TRAIN_CAP),
        "xgboost": Spec("XGBoost", "tfidf-stylometric-xgboost", sparse_features_small, False,
                        "beyond-unit", xgb),
    }


def make_pipeline(spec: Spec):
    """Raw text -> probability. Same object is what gets saved for deployment.

    `memory` caches fitted feature extractors, so models sharing a feature
    view (e.g. KNN/SVM/DT/RF on the dense view) pay for TF-IDF + SVD once.
    """
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    steps = [("features", spec.features())]
    if spec.scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("clf", spec.make()))
    return Pipeline(steps, memory=str(CACHE))


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------
def evaluate(y_true, y_prob) -> dict:
    import numpy as np
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 confusion_matrix, f1_score,
                                 precision_score, recall_score,
                                 roc_auc_score)
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(y_prob) >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_ai": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall_ai": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1_ai": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        # share of human text wrongly flagged as AI: the "false accusation" rate
        "false_positive_rate": round(float(fp / max(fp + tn, 1)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "n_test": int(len(y_true)),
    }


def aggregate_essays(sent_df: pd.DataFrame, probs: np.ndarray):
    """Word-count-weighted mean of sentence probabilities per document, the
    same rule the product uses for its document score."""
    d = sent_df.assign(p=probs)
    d["pw"] = d["p"] * d["w"]
    g = d.groupby("doc_id")
    prob = g["pw"].sum() / g["w"].sum()
    return g["label"].first().to_numpy(), prob.to_numpy()


def balanced_cap(df: pd.DataFrame, total: int) -> pd.DataFrame:
    per_class = total // 2
    return pd.concat([g.sample(min(len(g), per_class), random_state=SEED)
                      for _, g in df.groupby("label")])


def run_model(key: str, spec: Spec, data: dict, cross: bool):
    """Fit on the merged train set, then score every evaluation protocol."""
    train = data["train"] if spec.train_cap is None else balanced_cap(data["train"], spec.train_cap)
    essay, sent = data["essay_test"], data["sent_test"]

    t0 = time.perf_counter()
    pipe = make_pipeline(spec)
    pipe.fit(train["text"].tolist(), train["label"].to_numpy())
    fit_s = time.perf_counter() - t0

    probs = pipe.predict_proba(essay["text"].tolist())[:, 1]
    mask = essay["in_sent_test"].to_numpy()
    res = {
        "label": spec.label, "model_name": spec.model_name, "kind": spec.kind,
        "features": "dense" if spec.features is dense_features else "sparse",
        "scaled": spec.scale, "n_train": int(len(train)), "fit_seconds": round(fit_s, 1),
        "sentence": evaluate(sent["label"], probs[mask]),
        "per_source": {src: evaluate(g["label"], probs[mask][(sent["source"] == src).to_numpy()])
                       for src, g in sent.groupby("source")},
    }
    y_doc, p_doc = aggregate_essays(essay, probs)
    res["essay"] = evaluate(y_doc, p_doc)

    res["cross_source"] = {}
    if cross:
        sources = sorted(data["train"]["source"].unique())
        for src_in in sources:
            for src_out in sources:
                if src_in == src_out:
                    continue
                tr = data["train"][data["train"]["source"] == src_in]
                if spec.train_cap is not None:
                    tr = balanced_cap(tr, spec.train_cap)
                te = sent[sent["source"] == src_out]
                p = make_pipeline(spec)
                p.fit(tr["text"].tolist(), tr["label"].to_numpy())
                res["cross_source"][f"{src_in}->{src_out}"] = evaluate(
                    te["label"], p.predict_proba(te["text"].tolist())[:, 1])
    if res["cross_source"]:
        aucs = [m["roc_auc"] for m in res["cross_source"].values()]
        res["cross_auc_mean"] = round(float(np.mean(aucs)), 4)
        res["generalisation_gap_auc"] = round(res["sentence"]["roc_auc"] - res["cross_auc_mean"], 4)
    return pipe, res


def pick_final(results: dict, override: str | None) -> tuple[str, str]:
    if override:
        return override, f"chosen manually via --final {override}"
    with_cross = {k: r for k, r in results.items() if "cross_auc_mean" in r}
    if with_cross:
        best = max(with_cross, key=lambda k: (with_cross[k]["cross_auc_mean"],
                                               with_cross[k]["sentence"]["f1_ai"]))
        return best, "highest mean cross-source ROC-AUC (tie-break: in-distribution F1)"
    best = max(results, key=lambda k: results[k]["sentence"]["roc_auc"])
    return best, "highest in-distribution ROC-AUC (cross-source evaluation was skipped)"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
def comparison_tables(results: dict, hf: dict | None) -> str:
    f = lambda x: f"{x:.3f}"  # noqa: E731
    lines = ["### Table 1. In-distribution (grouped split, balanced per source and label)", "",
             "| Model | Features | Scaled | Unit | Sent. precision | Sent. recall | Sent. F1 | "
             "Sent. AUC | Brier | Human FPR | Essay F1 | Essay AUC | Fit (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results.values():
        s, e = r["sentence"], r["essay"]
        lines.append(f"| {r['label']} | {r['features']} | {'yes' if r['scaled'] else 'no'} | "
                     f"{r['kind']} | {f(s['precision_ai'])} | {f(s['recall_ai'])} | {f(s['f1_ai'])} | "
                     f"{f(s['roc_auc'])} | {f(s['brier_score'])} | {f(s['false_positive_rate'])} | "
                     f"{f(e['f1_ai'])} | {f(e['roc_auc'])} | {r['fit_seconds']} |")
    if hf:
        s = hf["metrics"]
        lines.append(f"| RoBERTa detector (pretrained; {hf.get('n_per_class', '?')} sentences per class) "
                     f"| n/a | n/a | beyond-unit | {f(s['precision_ai'])} | "
                     f"{f(s['recall_ai'])} | {f(s['f1_ai'])} | {f(s['roc_auc'])} | {f(s['brier_score'])} | "
                     f"{f(s['false_positive_rate'])} | - | - | - |")

    directions = sorted({d for r in results.values() for d in r["cross_source"]})
    if directions:
        head = "| Model |" + "".join(f" {d} P | {d} R | {d} F1 | {d} AUC |" for d in directions)
        head += " Mean cross AUC | AUC gap |"
        lines += ["", "### Table 2. Cross-source generalisation (train on one corpus, test on the other)", "",
                  head, "|---|" + "---|" * (4 * len(directions) + 2)]
        for r in results.values():
            cells = ""
            for d in directions:
                m = r["cross_source"].get(d)
                cells += (f" {f(m['precision_ai'])} | {f(m['recall_ai'])} | {f(m['f1_ai'])} | "
                          f"{f(m['roc_auc'])} |") if m else " - | - | - | - |"
            lines.append(f"| {r['label']} |{cells} {f(r.get('cross_auc_mean', float('nan')))} | "
                         f"{f(r.get('generalisation_gap_auc', float('nan')))} |")
    # Table 3: same fitted models, test sentences split by source. Shows where
    # each model is strong or weak. The RoBERTa detector was trained on HC3, so
    # only its DAIGT row is a genuinely unseen-data result.
    sources = sorted({s for r in results.values() for s in r["per_source"]})
    if sources:
        lines += ["", "### Table 3. In-distribution test sentences by source", "",
                  "| Model |" + "".join(f" {s} P | {s} R | {s} F1 | {s} AUC |" for s in sources),
                  "|---|" + "---|" * (4 * len(sources))]
        rows3 = [(r["label"], r["per_source"]) for r in results.values()]
        if hf and hf.get("per_source"):
            rows3.append(("RoBERTa detector (pretrained)", hf["per_source"]))
        for name, ps in rows3:
            cells = "".join((f" {f(ps[s]['precision_ai'])} | {f(ps[s]['recall_ai'])} | "
                             f"{f(ps[s]['f1_ai'])} | {f(ps[s]['roc_auc'])} |") if s in ps
                            else " - | - | - | - |" for s in sources)
            lines.append(f"| {name} |{cells}")
    return "\n".join(lines) + "\n"


def load_hf_eval(models_dir: Path = MODELS, data_dir: Path = DATA) -> dict | None:
    """RoBERTa results, only if they were produced on the current test split."""
    hf, split = models_dir / "hf_eval.json", data_dir / "test_split.jsonl"
    if hf.exists() and split.exists() and hf.stat().st_mtime > split.stat().st_mtime:
        return json.loads(hf.read_text())
    return None


# --------------------------------------------------------------------------
def main():
    import joblib

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=str(DEFAULT_DATASET))
    ap.add_argument("--fast", action="store_true", help="~10x smaller caps for smoke tests")
    ap.add_argument("--skip-cross", action="store_true", help="skip cross-source experiments")
    ap.add_argument("--models", default="all", help="comma list of: " + ",".join(model_zoo()))
    ap.add_argument("--final", default=None, help="force which model becomes final_model.pkl")
    ap.add_argument("--clear-cache", action="store_true")
    ap.add_argument("--table-only", action="store_true",
                    help="rebuild model_comparison.md from saved results (adds RoBERTa "
                         "after `python -m ml.evaluate_hf`); no training")
    args = ap.parse_args()

    # --fast writes to ml/_smoke/ so a smoke test can never overwrite the real
    # model, test split or comparison tables that the app and report rely on.
    root = BACKEND / "ml" / "_smoke" if args.fast else None
    models_dir = root / "models" if root else MODELS
    data_dir = root / "data" if root else DATA
    models_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    if args.table_only:
        saved = json.loads((models_dir / "model_comparison.json").read_text())
        (models_dir / "model_comparison.md").write_text(
            comparison_tables(saved, load_hf_eval(models_dir, data_dir)))
        print("Rebuilt model_comparison.md")
        return
    if args.clear_cache:
        shutil.rmtree(CACHE, ignore_errors=True)
    scale = 0.1 if args.fast else 1.0

    print(f"Loading {args.data} ...", flush=True)
    df = load_dataset(args.data)
    print(df.groupby(CELL).size().unstack().to_string(), flush=True)
    if (df["generator"] == "unknown").all():
        print("NOTE: no `generator` column; held-out-generator tests need it.", flush=True)

    data = build_datasets(df, scale)
    print({k: len(v) for k, v in data.items()}, flush=True)
    # Persist exactly the sentences used, so (a) the HF model is scored on the
    # identical test set and (b) the submitted dataset contains only what the
    # final model was trained/tested on.
    for name, table in (("train_split", data["train"]), ("test_split", data["sent_test"])):
        with open(data_dir / f"{name}.jsonl", "w") as fh:
            for r in table.itertuples():
                fh.write(json.dumps({"text": r.text, "label": int(r.label), "source": r.source,
                                     "generator": r.generator, "doc_id": r.doc_id}) + "\n")

    zoo = model_zoo()
    wanted = list(zoo) if args.models == "all" else args.models.split(",")
    pipes, results = {}, {}
    for key in wanted:
        print(f"\n=== {zoo[key].label} ===", flush=True)
        try:
            pipes[key], results[key] = run_model(key, zoo[key], data, not args.skip_cross)
        except ImportError as exc:
            print(f"  skipped ({exc})", flush=True)
            continue
        s = results[key]["sentence"]
        print(f"  sentence F1={s['f1_ai']} AUC={s['roc_auc']}  essay AUC={results[key]['essay']['roc_auc']}"
              f"  cross AUC={results[key].get('cross_auc_mean')}  fit={results[key]['fit_seconds']}s",
              flush=True)

    final_key, reason = pick_final(results, args.final)
    if final_key not in results:
        sys.exit(f"--final {final_key!r} was not trained in this run; trained: {list(results)}")
    final = results[final_key]
    print(f"\nFinal model: {final['label']} ({reason})", flush=True)

    hf = load_hf_eval(models_dir, data_dir)
    if hf is None:
        print("NOTE: hf_eval.json is older than the new test split; run "
              "`python -m ml.evaluate_hf` then `python -m ml.train --table-only` "
              "to add RoBERTa to the comparison table.", flush=True)
    table_md = comparison_tables(results, hf)
    print("\n" + table_md)

    version = f"{date.today().isoformat()}-merged"
    joblib.dump(pipes[final_key], models_dir / "final_model.pkl", compress=3)
    # The FastAPI StatisticalDetector still loads this name; keep both in sync.
    shutil.copyfile(models_dir / "final_model.pkl", models_dir / "statistical_model.joblib")
    (models_dir / "model_comparison.md").write_text(table_md)
    (models_dir / "model_comparison.json").write_text(json.dumps(results, indent=2))
    (models_dir / "statistical_model.meta.json").write_text(json.dumps({
        "model_name": final["model_name"],
        "model_key": final_key,  # key into model_zoo(); lets other scripts rebuild the architecture
        "version": version,
        "dataset": "merged DAIGT v2 + HC3 (dataprep/merged_dataset.csv), sentence-level, "
                   "document-grouped 80/20 split, balanced per (source, label)",
        "train_sentences": final["n_train"],
        "test_sentences": final["sentence"]["n_test"],
        "metrics": final["sentence"],
        "essay_level_metrics": final["essay"],
        "cross_source_metrics": final["cross_source"],
        "generalisation_gap_auc": final.get("generalisation_gap_auc"),
        "problem_definition": "Generalise to unseen AI-generated text; accuracy on a random "
                              "split is a reference point, not the selection criterion.",
        "selection_criterion": reason,
        "candidates": {k: {"cross_auc_mean": r.get("cross_auc_mean"),
                           "sentence_f1": r["sentence"]["f1_ai"],
                           "sentence_auc": r["sentence"]["roc_auc"]}
                       for k, r in results.items()},
    }, indent=2))
    print(f"Saved final_model.pkl, statistical_model.joblib, meta.json, "
          f"model_comparison.{{md,json}} to {models_dir}")


if __name__ == "__main__":
    main()
