"""FastAPI application: the scoring endpoint and health probe."""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .aggregate import bootstrap_ci, document_band, weighted_mean
from .detectors import registry
from .schemas import (DocumentScore, HealthResponse, Meta, ScoreRequest,
                      ScoreResponse, SentenceScore, band_for)
from .sentences import split_sentences

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AI-Generated Content Detection API",
    version="1.0.0",
    description="Sentence-level and document-level AI-generation scoring "
                "with a swappable detection backend.",
)

# Allow any localhost origin: Vite auto-bumps its port (5173 → 5174, …)
# when the default is taken, and this API uses no cookies/credentials, so
# pinning exact dev ports only causes spurious CORS preflight failures.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_WORDS_RELIABLE = 30
MIN_SENTENCES_RELIABLE = 3


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    detector, _ = registry.resolve()
    avail = registry.availability()
    return HealthResponse(
        status="ok",
        active_method=detector.name,
        available_methods=[k for k, v in avail.items() if v],
    )


@app.post("/api/v1/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    sents = split_sentences(req.text)
    if not sents:
        raise HTTPException(
            status_code=422,
            detail="No sentences found. Paste at least one full English "
                   "sentence and try again.",
        )

    try:
        detector, fallback_used = registry.resolve()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    raw_scores = detector.score_sentences([s.text for s in sents])
    raw_scores = [min(max(s, 0.0), 1.0) for s in raw_scores]

    sentence_scores = [
        SentenceScore(
            text=s.text, start=s.start, end=s.end,
            score=round(score_i, 4), band=band_for(score_i),
            word_count=s.word_count,
        )
        for s, score_i in zip(sents, raw_scores)
    ]

    weights = [float(s.word_count) for s in sents]
    doc_score = weighted_mean(raw_scores, weights)
    ci_low, ci_high = bootstrap_ci(raw_scores, weights)
    total_words = sum(s.word_count for s in sents)

    warnings: list[str] = []
    if total_words < MIN_WORDS_RELIABLE or len(sents) < MIN_SENTENCES_RELIABLE:
        warnings.append(
            "Text is very short; scores on short passages are unreliable "
            "and the confidence interval is wide. Provide at least "
            f"{MIN_SENTENCES_RELIABLE} sentences / {MIN_WORDS_RELIABLE} words "
            "for a more meaningful estimate."
        )
    if fallback_used:
        warnings.append(
            "The primary transformer model was unavailable; results come "
            "from the offline statistical model, which is less accurate."
        )

    return ScoreResponse(
        sentences=sentence_scores,
        document=DocumentScore(
            score=round(doc_score, 4),
            ci_low=round(ci_low, 4), ci_high=round(ci_high, 4),
            band=document_band(doc_score, [s.band for s in sentence_scores]),
            word_count=total_words, sentence_count=len(sents),
        ),
        meta=Meta(
            method=detector.name, model_name=detector.model_name,
            version=detector.version, fallback_used=fallback_used,
            warnings=warnings,
        ),
    )
