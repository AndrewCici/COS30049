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

## Retrain the fallback model

```bash
cd backend
../.venv/bin/python -m ml.train         # downloads HC3, trains, evaluates
../.venv/bin/python -m ml.evaluate_hf   # scores the HF model on the same test split
```

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
