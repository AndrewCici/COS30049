"""Pydantic models defining the API contract.

This module is the single source of truth for the request/response shape.
Detectors are swappable behind it; nothing here may change when the
underlying model changes (that is the whole point of the contract).
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import config

# Band thresholds are part of the contract: the UI renders whatever the API
# sends, so legend and highlights can never drift out of sync with scoring.
BAND_THRESHOLDS = {"low_below": 0.35, "high_at_or_above": 0.65}

# Binary verdict threshold: 0.5 is the natural decision boundary for a
# calibrated probability of the positive ("AI-generated") class.
VERDICT_THRESHOLD = 0.5

Band = Literal["low", "medium", "high"]
DocumentBand = Literal["low", "medium", "high", "mixed"]
Verdict = Literal["ai-generated", "human-made"]


def band_for(score: float) -> Band:
    if score < BAND_THRESHOLDS["low_below"]:
        return "low"
    if score >= BAND_THRESHOLDS["high_at_or_above"]:
        return "high"
    return "medium"


def verdict_for(score: float) -> Verdict:
    return "ai-generated" if score >= VERDICT_THRESHOLD else "human-made"


def confidence_for(score: float) -> float:
    """Probability of the predicted class (not of 'AI-generated')."""
    return score if score >= VERDICT_THRESHOLD else 1.0 - score


class ScoreRequest(BaseModel):
    text: str = Field(
        ..., min_length=config.MIN_TEXT_CHARS, max_length=config.MAX_TEXT_CHARS,
        description="English passage to analyse.",
    )

    @field_validator("text")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must contain more than whitespace.")
        return value

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": (
                        "Furthermore, it is important to note that this "
                        "passage demonstrates a formal, structured register. "
                        "My dog just knocked a mug off the table, so this "
                        "sentence is a bit less tidy."
                    )
                }
            ]
        }
    }


class SentenceScore(BaseModel):
    text: str
    start: int = Field(..., description="Character offset into the original text.")
    end: int
    score: float = Field(..., ge=0.0, le=1.0)
    band: Band
    word_count: int


class DocumentScore(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0,
                         description="Length-weighted mean of sentence scores.")
    ci_low: float = Field(..., ge=0.0, le=1.0)
    ci_high: float = Field(..., ge=0.0, le=1.0)
    confidence_level: float = 0.95
    band: DocumentBand
    verdict: Verdict = Field(
        ..., description=f"Binary call at threshold {VERDICT_THRESHOLD}.")
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Probability of the predicted class (verdict), not of "
                    "'ai-generated' specifically.")
    word_count: int
    sentence_count: int


class NormalisationInfo(BaseModel):
    applied: bool = Field(
        ..., description="False when NORMALISE_INPUT=off (demo-only; see "
                         "security/evasion/REPORT.md).")
    format_chars_removed: int = Field(
        ..., description="Invisible Unicode format characters (category Cf) "
                         "stripped before scoring.")
    combining_marks_removed: int = Field(
        ..., description="Combining marks NFKC could not reattach to a "
                         "precomposed character, then stripped before "
                         "scoring.")
    confusables_mapped: int = Field(
        ..., description="Cyrillic/Greek homoglyphs mapped to their Latin "
                         "equivalent before scoring.")


class Meta(BaseModel):
    method: str
    model_name: str
    version: str
    fallback_used: bool
    bands: dict = Field(default_factory=lambda: dict(BAND_THRESHOLDS))
    warnings: list[str] = Field(default_factory=list)
    normalisation: NormalisationInfo


class ScoreResponse(BaseModel):
    sentences: list[SentenceScore]
    document: DocumentScore
    meta: Meta

    # A real response from the statistical model to the ScoreRequest
    # example above, so /docs shows matching input and output.
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "sentences": [
                        {
                            "text": "Furthermore, it is important to note that "
                                    "this passage demonstrates a formal, "
                                    "structured register.",
                            "start": 0, "end": 98, "score": 0.9916,
                            "band": "high", "word_count": 14,
                        },
                        {
                            "text": "My dog just knocked a mug off the table, so "
                                    "this sentence is a bit less tidy.",
                            "start": 99, "end": 176, "score": 0.3044,
                            "band": "low", "word_count": 17,
                        },
                    ],
                    "document": {
                        "score": 0.6148, "ci_low": 0.3044, "ci_high": 0.9916,
                        "confidence_level": 0.95, "band": "mixed",
                        "verdict": "ai-generated", "confidence": 0.6148,
                        "word_count": 31, "sentence_count": 2,
                    },
                    "meta": {
                        "method": "statistical",
                        "model_name": "tfidf-stylometric-logreg",
                        "version": "2026-10-07-merged",
                        "fallback_used": False,
                        "bands": dict(BAND_THRESHOLDS),
                        "warnings": [
                            "Text is very short; scores on short passages are "
                            "unreliable and the confidence interval is wide. "
                            "Provide at least 3 sentences / 30 words for a "
                            "more meaningful estimate."
                        ],
                        "normalisation": {
                            "applied": True, "format_chars_removed": 0,
                            "combining_marks_removed": 0,
                            "confusables_mapped": 0,
                        },
                    },
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    status: Literal["ok"]
    active_method: str
    available_methods: list[str]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"status": "ok", "active_method": "statistical",
                 "available_methods": ["statistical"]}
            ]
        }
    }


class InputLimits(BaseModel):
    min_text_chars: int
    max_text_chars: int
    max_sentences: int


class ModelInfoResponse(BaseModel):
    model_name: str
    version: str
    dataset: str
    metrics: dict
    essay_level_metrics: dict
    bands: dict = Field(default_factory=lambda: dict(BAND_THRESHOLDS))
    input_limits: InputLimits

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model_name": "tfidf-stylometric-logreg",
                    "version": "2026-10-07-merged",
                    "dataset": "merged DAIGT v2 + HC3 (dataprep/merged_dataset.csv), "
                               "sentence-level, document-grouped 80/20 split, "
                               "balanced per (source, label)",
                    "metrics": {
                        "accuracy": 0.9005, "precision_ai": 0.8861,
                        "recall_ai": 0.924, "f1_ai": 0.9046, "roc_auc": 0.9652,
                        "brier_score": 0.0743, "false_positive_rate": 0.124,
                        "confusion_matrix": [[6240, 883], [565, 6868]],
                        "n_test": 14556,
                    },
                    "essay_level_metrics": {
                        "accuracy": 0.9642, "f1_ai": 0.9644, "roc_auc": 0.9874,
                        "false_positive_rate": 0.0544, "n_test": 1925,
                    },
                    "bands": dict(BAND_THRESHOLDS),
                    "input_limits": {"min_text_chars": 20,
                                     "max_text_chars": 12000,
                                     "max_sentences": 300},
                }
            ]
        }
    }


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable SNAKE_CASE error code.")
    message: str = Field(..., description="Human-readable explanation.")
    request_id: str = Field(..., description="Correlates with server-side logs.")


class ErrorResponse(BaseModel):
    error: ErrorDetail

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"error": {"code": "VALIDATION_ERROR",
                           "message": "The text is too short: enter at least "
                                      "20 characters.",
                           "request_id": "3f2b8c1e-6a4d-4e0f-9b7a-2c5d8e1f0a93"}}
            ]
        }
    }
