# Model Evaluation (Stage 2)

## Dataset

**HC3** (`Hello-SimpleAI/HC3`, `all.jsonl`): 24,322 questions, each paired
with human answers (Reddit ELI5, finance, medicine, open QA, wiki CS/AI)
and ChatGPT answers to the same question.

Preparation (see `backend/ml/train.py`):

- Answers are split into sentences with the app's own splitter (the unit
  the product scores), keeping sentences of 5–120 words.
- **80/20 train/test split grouped by question** — no answer (human or AI)
  to any test question appears in training, preventing topic leakage.
- Balanced sampling: 40,000 sentences per class for training, 8,000 per
  class for testing (seed 42, reproducible).

## Results on the held-out test set

| Metric (positive class = AI) | Statistical model (ours) | HF transformer (primary) |
|---|---|---|
| Accuracy | **0.962** | **0.988** |
| Precision | 0.943 | 0.989 |
| Recall | 0.984 | 0.987 |
| F1 | 0.963 | 0.988 |
| ROC AUC | 0.993 | 0.999 |
| Brier score (calibration, lower = better) | 0.031 | 0.010 |
| Test sentences | 16,000 | 1,500 (balanced subsample) |

- **Statistical model** — logistic regression over word TF-IDF (1–2 grams),
  char TF-IDF (2–4 grams) and 10 stylometric features; 2.6 MB artifact,
  CPU-only, loads in <1 s. Confusion matrix: 474 human sentences flagged
  as AI (5.9% false-positive rate), 131 AI sentences missed.
- **HF transformer** — `Hello-SimpleAI/chatgpt-detector-roberta`, evaluated
  on a balanced subsample of the same split (CPU inference cost; n=1,500
  gives ±1.6% margin at 95% confidence). 8 false positives / 10 false
  negatives.

Reproduce with `python -m ml.train` and `python -m ml.evaluate_hf`.

## Limitations — read before trusting any number

1. **The transformer's figures are optimistic.** It was fine-tuned by its
   authors on HC3 itself, so this evaluation is in-domain for it; on text
   types outside HC3 (essays, marketing copy, fiction) both models will do
   worse than the table suggests.
2. **ChatGPT-era data.** HC3 was collected in 2022–23 from ChatGPT
   (GPT-3.5). Newer models (GPT-4/5, Claude, Gemini) write differently;
   detection performance against them is unmeasured here and likely lower.
3. **False positives are the costly error.** ~6% of genuinely human
   sentences are flagged AI by the fallback model. This is why the product
   reports confidence intervals, uses banded wording ("likely", "unclear"),
   and warns that scores are not proof of authorship.
4. **English only.** Both models are trained exclusively on English; other
   languages produce meaningless scores.
5. **Short sentences carry little signal.** Sentences under ~5 words were
   excluded from training; the API warns when a document is under 3
   sentences or 30 words.
6. **Adversarial robustness is untested.** Paraphrasing tools and light
   human editing are known to defeat detectors of both families.
7. **Fairness caveat.** Published work (Liang et al., 2023) shows detectors
   over-flag non-native English writing; nothing in this training pipeline
   corrects for that. The UI's limitations panel states it.

## Why these two methods

- The **transformer** is primary because contextual embeddings capture
  fluency/register patterns n-grams cannot, and its Brier score shows
  better-calibrated probabilities — which the UI displays directly.
- The **linear model** is the fallback because it is small, dependency-light
  and offline; it costs ~2.6 points of accuracy but keeps the product
  functional (with an explicit warning) when the transformer can't load.
  Its probabilities are also well-calibrated enough to share the same UI
  scale, so swapping methods never changes the meaning of the display.
