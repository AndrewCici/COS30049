"""Pydantic models defining the API contract.

This module is the single source of truth for the request/response shape.
Detectors are swappable behind it; nothing here may change when the
underlying model changes (that is the whole point of the contract).
"""
from typing import Literal

from pydantic import BaseModel, Field

# Band thresholds are part of the contract: the UI renders whatever the API
# sends, so legend and highlights can never drift out of sync with scoring.
BAND_THRESHOLDS = {"low_below": 0.35, "high_at_or_above": 0.65}

Band = Literal["low", "medium", "high"]
DocumentBand = Literal["low", "medium", "high", "mixed"]


def band_for(score: float) -> Band:
    if score < BAND_THRESHOLDS["low_below"]:
        return "low"
    if score >= BAND_THRESHOLDS["high_at_or_above"]:
        return "high"
    return "medium"


class ScoreRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000,
                      description="English passage to analyse.")


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
