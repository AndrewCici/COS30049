# AI-Generated Content Detection — Project Plan

**Course:** COS30049 Innovation Project
**Deliverable:** A web tool that scores English text for AI-generated content at sentence level and document level.

---

## 1. Problem statement

Given a pasted passage of English text, the system must report:

1. **Sentence-level scores** — for every sentence, a probability in [0, 1] that the sentence is AI-generated, visualised as a colour-coded highlight with a fixed legend.
2. **Document-level score** — a length-weighted average of sentence scores, reported **with a 95% confidence interval**, not a bare point estimate.

Detection of AI-generated text is inherently uncertain: no published detector is reliable enough to justify a single authoritative number, and false accusations (e.g. of students) have real costs. The interval and the per-sentence breakdown are therefore *product requirements*, not statistical decoration — they communicate uncertainty honestly (Nielsen #1: visibility of system status; #5/#9: helping users recognise, diagnose, and not over-trust results).

## 2. Architecture

```
┌──────────────────────────┐        JSON over HTTP        ┌───────────────────────────────┐
│  React + MUI (Vite, TS)  │  ──── Axios POST /score ───▶ │  FastAPI backend              │
│  - Paste box, Analyze    │                              │  - sentence segmentation      │
│  - Highlighted sentences │ ◀──── scores + CI ────────── │  - Detector interface         │
│  - Legend + doc gauge    │                              │     ├─ HF transformer (1st)   │
└──────────────────────────┘                              │     ├─ trained statistical    │
                                                          │     └─ mock (stage 1 / tests) │
                                                          └───────────────────────────────┘
```

### Why this shape

- **The API contract is fixed before any model exists.** The frontend is built in Stage 1 against a `mock` detector that honours the exact same request/response schema. When the trained model lands in Stage 3, *nothing* in the frontend changes. This is the "swappable detection method" requirement made concrete: the contract lives in `backend/app/schemas.py`, and every detector implements one interface (`Detector.score_sentences`).
- **Segmentation and aggregation live in the backend, not the model.** Sentence splitting, length-weighting and the confidence interval are deliberately *outside* the detector interface. Upgrading the model can never change how scores are aggregated or how sentences are defined, so results stay comparable across model versions.
- **Fallback chain, not fallback flag.** The backend resolves a detector at request time: HuggingFace classifier → locally trained statistical model → error. If the transformer can't be loaded (no weights downloaded, offline machine, out of memory), the statistical model answers instead, and the response's `meta.method` field tells the user which method actually ran (Nielsen #1: never pretend the primary model answered when it didn't).

### API contract (frozen from Stage 1)

`POST /api/v1/score` with `{"text": "..."}` returns:

```json
{
  "sentences": [
    {"text": "…", "start": 0, "end": 42, "score": 0.87, "band": "high", "word_count": 9}
  ],
  "document": {
    "score": 0.61,
    "ci_low": 0.44, "ci_high": 0.78,
    "confidence_level": 0.95,
    "band": "mixed",
    "word_count": 214, "sentence_count": 12
  },
  "meta": {"method": "hf-transformer", "model_name": "…", "version": "…", "fallback_used": false}
}
```

`GET /api/v1/health` reports which detectors are available (drives a status chip in the UI).

## 3. Scoring design

- **Sentence scores** come straight from the active detector (classifier probability of the "AI" class).
- **Document score** = Σ(wᵢ·sᵢ)/Σ(wᵢ) where wᵢ is the sentence's word count. Rationale: a 40-word AI paragraph should dominate a 3-word human interjection; weighting by length approximates "what fraction of the *text* is AI-like".
- **95% CI** by weighted bootstrap: resample sentences with replacement (probability ∝ existence, weight carried along), recompute the weighted mean 2,000 times, take the 2.5th/97.5th percentiles. Chosen over a normal-approximation interval because sentence scores are bounded in [0,1], often bimodal (mixed documents), and few in number — the nonparametric bootstrap makes no distributional assumption. For documents of 1–2 sentences the interval is reported at its widest honest form and the UI adds a "very short text — low reliability" warning (Nielsen #5: error prevention).
- **Bands** (fixed thresholds, shared by legend, tooltips and text labels): `low` < 0.35 ≤ `medium` < 0.65 ≤ `high`. The document additionally uses `mixed` when sentence bands disagree strongly. Thresholds are part of the API response so the UI never hard-codes them out of sync.

## 4. UX commitments (checked in Stage 1 and re-verified in Stage 3)

| Principle | Where it shows up |
|---|---|
| Nielsen 1 — Visibility of status | Loading indicator during scoring; method chip ("Transformer" / "Statistical fallback"); live word/char count |
| Nielsen 2 — Match with real world | "Likely human-written / Unclear / Likely AI-generated" wording, not raw logits |
| Nielsen 3 — User control & freedom | Clear button, re-analyse after edit, results dismissible; no irreversible actions |
| Nielsen 4 — Consistency | MUI components throughout; one fixed legend; same band wording everywhere |
| Nielsen 5 — Error prevention | Analyze disabled for empty/too-short input with explanation; length limit shown before submit |
| Nielsen 6 — Recognition over recall | Legend always visible next to results; tooltips repeat band meaning |
| Nielsen 7 — Flexibility & efficiency | Ctrl/Cmd+Enter to analyse; sample-text button for first-time users |
| Nielsen 8 — Minimalist design | One primary action per screen state; details (CI method, model info) in a collapsible section |
| Nielsen 9 — Help users with errors | Human-readable API error messages with suggested action; fallback notice instead of hard failure |
| Nielsen 10 — Help & documentation | "How it works & limitations" section, including what the tool cannot prove |
| Shneiderman 1–8 | Consistency (4↔S1), shortcuts (S2), informative feedback (S3), closure via result summary (S4), simple error handling (S5), reversal of actions (S6), user in control (S7), low memory load (S8) |
| **WCAG 1.4.1** | Colour is never the only cue: every highlighted sentence carries a text underline style *and* a tooltip + accessible label with the band name and numeric score; the legend pairs each colour with a text label and score range; the document gauge prints the number and band as text. Palette chosen to also differ in luminance for colour-blind users. |

## 5. Stages

**Stage 1 — UI prototype + plan (no real model).**
Frontend built against the frozen contract; backend serves a deterministic `mock` detector (hash-based pseudo-scores) so the UI is fully exercisable. Deliverables: this plan, running prototype, design-decision log.

**Stage 2 — Trained model + documented evaluation.**
Train a logistic-regression classifier over TF-IDF n-grams + stylometric features on the HC3 corpus (human vs ChatGPT answers). Evaluate on a held-out split: accuracy, precision, recall, F1, plus calibration check (scores must be usable as probabilities, since the UI presents them as such). Deliverable: `docs/EVALUATION.md` with dataset description and limitations. The pretrained HuggingFace transformer (`Hello-SimpleAI/chatgpt-detector-roberta`) is evaluated on the same split for comparison and serves as the primary method.

**Stage 3 — Integration + tests.**
Wire both detectors behind the interface with the fallback chain; automated tests: API contract, sentence segmentation, weighted mean + CI properties, fallback behaviour, band consistency. End-to-end check in a browser.

## 6. Risks

- **Detector unreliability** — mitigated by CI display, banded wording, explicit limitations section; the tool is framed as *screening*, never proof.
- **Model download unavailability** — the statistical model is trained locally and committed as a small artifact; the app degrades gracefully and says so.
- **Short texts** — flagged as low-reliability in both API (`meta.warnings`) and UI.
- **Non-English input** — out of scope; documented limitation (training data is English).
