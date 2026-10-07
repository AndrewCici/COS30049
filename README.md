# AI Content Detector

Paste an English passage → get a sentence-level AI-generation probability
(colour-coded highlights with a fixed legend) and a document-level score
reported with a 95% confidence interval.

- **Frontend:** React + TypeScript + MUI (Vite), calling the API via Axios.
- **Backend:** FastAPI with a swappable detector behind one fixed contract:
  1. `hf-transformer` — pretrained `Hello-SimpleAI/chatgpt-detector-roberta` (primary)
  2. `statistical` — locally trained TF-IDF + stylometric logistic regression (offline fallback)
  3. `mock` — deterministic pseudo-scores (Stage-1 prototype / tests; opt-in only)

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the architecture and staged plan,
and [docs/EVALUATION.md](docs/EVALUATION.md) for the model evaluation.

## Run it

Backend (Python ≥ 3.11):

```bash
cd backend
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
../.venv/bin/uvicorn app.main:app --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

The first `/score` request downloads the transformer weights (~500 MB) if
absent; when that fails (offline), the app automatically answers with the
statistical model and says so in the UI.

## Machine-learning pipeline (Assignment 2)

All commands run from the repository root unless stated otherwise.

**1. Environment (conda)**

```bash
conda env create -f environment.yml
conda activate cos30049
```

**2. Data processing** (Person B, `dataprep/data_prep.py`). Place the raw files
first: DAIGT v2 `train_v2_drcat_02.csv` (Kaggle `thedrcat/daigt-v2-train-dataset`)
in `dataprep/archive/`, and HC3 `all.jsonl` (Hugging Face `Hello-SimpleAI/HC3`)
in `dataprep/`.
The processed dataset is shipped as `dataprep/merged_dataset.csv.zip`.
To skip step 2, unzip it in place so that `dataprep/merged_dataset.csv` exists:

    cd dataprep && unzip merged_dataset.csv.zip && cd ..

```bash
python dataprep/data_prep.py            # writes dataprep/merged_dataset.csv (+ EDA plots)
python dataprep/data_prep.py --skip-eda # same, without plots
```

The merged file has one row per document with columns `text, label (0=human,
1=AI), source (DAIGT_v2 | HC3), topic, group, generator, generator_family`.

**3. Train and compare models** (Person A, `backend/ml/train.py`)

```bash
cd backend
python -m ml.train                  # full run (tens of minutes); writes models/
python -m ml.train --fast           # ~10x smaller smoke test; writes ml/_smoke/ only
python -m ml.evaluate_hf 8000       # pretrained RoBERTa on the same test sentences
python -m ml.train --table-only     # add the RoBERTa row to models/model_comparison.md
```

Outputs in `backend/models/`: `final_model.pkl` (selected model),
`statistical_model.meta.json` (metrics, selection criterion),
`model_comparison.md/json` (all models, three evaluation protocols). The exact
sentences used are saved in `backend/ml/data/train_split.jsonl` and
`test_split.jsonl`.

The exact train/test sentences used for the reported results are shipped in
`backend/ml/data/train_split.jsonl` and `test_split.jsonl`.

**4. Predict with the trained model**

```bash
cd backend
python -m ml.predict "Furthermore, it is important to note that this is a test. lol idk man."
python -m ml.predict --file essay.txt
```

Or start the web app (see "Run it" above): `POST /api/v1/score`.

**5. Clustering, held-out evaluation and feature EDA** (Person C, `backend/ml/`)

Both scripts read the merged dataset from `backend/ml/data/merged_dataset_v2.csv`
(the folder is git-ignored). Copy the output of step 2 there first:

```bash
mkdir -p backend/ml/data
cp dataprep/merged_dataset.csv backend/ml/data/merged_dataset_v2.csv
cd backend/ml
python cluster_and_eval.py     # several minutes: K-Means + two retrainings
python eda_features.py         # about 1-2 minutes
```

`cluster_and_eval.py`:
- clusters the AI-generated documents with K-Means on the ten stylometric
  features (`StandardScaler`, K = 2-8 compared by elbow and silhouette, K = 6 kept),
  prints each cluster's size, distinctive features and the document closest
  to its centre, and saves `elbow_plot.png`;
- runs the held-out generator test: the final model configuration from
  `ml/train.py` is trained once with and once without the Mistral family and
  both are scored on the same balanced human/Mistral test sentences. Metrics
  are saved to `heldout_family_mistral.json` and eight random false positives
  and false negatives are printed for error analysis (seed 42).

`eda_features.py` compares the 20 stylometric and discourse features on
10,000 human and 10,000 AI texts and saves `eda_feature_differences.png` and
`eda_feature_summary.csv`. Another dataset path can be passed as an argument:
`python eda_features.py path/to/file.csv`.

`holdout_daigt_full_hc3model.json` and `holdout_daigt_sentences_hc3model.json`
are results of an earlier test with the HC3-only model, kept for reference.

## Tests

```bash
cd backend && ../.venv/bin/pytest tests/ -q
```

## API

`POST /api/v1/score` `{"text": "..."}` → sentence scores (+offsets, bands),
document score with 95% CI, and `meta` describing which detector answered.
`GET /api/v1/health` → active + available methods. Interactive docs at
`http://localhost:8000/docs`.

## Environment variables


| Variable | Effect |
|---|---|
| `AIDETECT_METHOD` | Force one method (`hf-transformer`, `statistical`, `mock`) |
| `AIDETECT_ALLOW_MOCK` | `1` adds the mock to the end of the fallback chain |
| `AIDETECT_HF_MODEL` | Override the HuggingFace model id |
