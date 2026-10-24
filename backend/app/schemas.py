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


class Meta(BaseModel):
    method: str
    model_name: str
    version: str
    fallback_used: bool
    bands: dict = Field(default_factory=lambda: dict(BAND_THRESHOLDS))
    warnings: list[str] = Field(default_factory=list)


class ScoreResponse(BaseModel):
    sentences: list[SentenceScore]
    document: DocumentScore
    meta: Meta


class HealthResponse(BaseModel):
    status: Literal["ok"]
    active_method: str
    available_methods: list[str]


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


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable SNAKE_CASE error code.")
    message: str = Field(..., description="Human-readable explanation.")
    request_id: str = Field(..., description="Correlates with server-side logs.")


class ErrorResponse(BaseModel):
    error: ErrorDetail
