"""FastAPI application: the scoring endpoint, health probe and model info."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from . import config
from .aggregate import bootstrap_ci, document_band, weighted_mean
from .detectors import registry
from .model_integrity import ModelIntegrityError
from .schemas import (BAND_THRESHOLDS, DocumentScore, ErrorResponse,
                      HealthResponse, InputLimits, Meta, ModelInfoResponse,
                      ScoreRequest, ScoreResponse, SentenceScore, band_for,
                      confidence_for, verdict_for)
from .sentences import split_sentences
from .statistical_meta import load_meta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ApiError(StarletteHTTPException):
    """An HTTPException carrying a stable machine-readable error code,
    surfaced in the shared `{"error": {...}}` response envelope."""

    def __init__(self, status_code: int, code: str, message: str,
                headers: dict | None = None):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = code


_CODE_BY_STATUS = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The statistical model is loaded exactly once here, not lazily on the
    # first request, and its integrity is checked first: a corrupted or
    # tampered artifact must stop the server from starting, not silently
    # serve wrong predictions. Skipped only when "statistical" is not even
    # in the active resolution chain (e.g. tests forcing another method).
    if "statistical" in registry.preferred_order():
        try:
            detector = registry.get("statistical")
            detector.load_verified()
            app.state.detector = detector
        except ModelIntegrityError:
            logger.error("Statistical model failed its integrity check; "
                        "refusing to start.")
            raise
    yield


app = FastAPI(
    title="AI-Generated Content Detection API",
    version="1.0.0",
    description="Sentence-level and document-level AI-generation scoring "
                "with a swappable detection backend. The default detector "
                "is a locally trained statistical model that needs no "
                "network access; a pretrained transformer is available as "
                "an opt-in alternative (see AIDETECT_ENABLE_HF).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Tags every request/response with a UUID so a client-reported problem
    can be matched to the corresponding server-side log line."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)

MIN_WORDS_RELIABLE = 30
MIN_SENTENCES_RELIABLE = 3


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_body(code: str, message: str, request_id: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = getattr(exc, "error_code", None) or _CODE_BY_STATUS.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message, _request_id(request)),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p != "body")
    message = f"{field}: {first['msg']}" if field else first["msg"]
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", message, _request_id(request)),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = _request_id(request)
    # The traceback is logged server-side, keyed by request_id, and never
    # returned to the client.
    logger.exception("Unhandled error [request_id=%s]", request_id)
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_ERROR", "An unexpected error occurred. Please try again.",
            request_id,
        ),
    )


_ERROR_RESPONSES = {
    413: {"model": ErrorResponse, "description": "Request body too large."},
    422: {"model": ErrorResponse, "description": "Invalid input."},
    503: {"model": ErrorResponse, "description": "No detection method is available."},
    500: {"model": ErrorResponse, "description": "Unexpected server error."},
}


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service and detector availability",
    description="Reports which detection method is currently active and "
                "which methods are available, without triggering a model "
                "download. Used to drive a status indicator in the UI.",
)
def health() -> HealthResponse:
    detector, _ = registry.resolve()
    avail = registry.availability()
    return HealthResponse(
        status="ok",
        active_method=detector.name,
        available_methods=[k for k, v in avail.items() if v],
    )


@app.get(
    "/api/v1/model-info",
    response_model=ModelInfoResponse,
    tags=["Model"],
    summary="Statistical model description and evaluation metrics",
    description="Reports the active statistical model's identity, training "
                "data summary, held-out evaluation metrics, scoring band "
                "thresholds and the input limits enforced by /score. The "
                "front end uses this to render an 'About the model' panel "
                "and to validate input before submitting it.",
    responses={503: _ERROR_RESPONSES[503], 500: _ERROR_RESPONSES[500]},
)
def model_info() -> ModelInfoResponse:
    meta = load_meta()
    if meta is None:
        raise ApiError(503, "MODEL_INFO_UNAVAILABLE",
                       "Model metadata is not available on this server.")
    return ModelInfoResponse(
        model_name=meta.get("model_name", "unknown"),
        version=meta.get("version", "unknown"),
        dataset=meta.get("dataset", "unknown"),
        metrics=meta.get("metrics", {}),
        essay_level_metrics=meta.get("essay_level_metrics", {}),
        bands=dict(BAND_THRESHOLDS),
        input_limits=InputLimits(
            min_text_chars=config.MIN_TEXT_CHARS,
            max_text_chars=config.MAX_TEXT_CHARS,
            max_sentences=config.MAX_SENTENCES,
        ),
    )


@app.post(
    "/api/v1/score",
    response_model=ScoreResponse,
    tags=["Detection"],
    summary="Score a passage for AI-generated content",
    description="Splits the passage into sentences, scores each with the "
                "active detector, and aggregates them into a length-"
                "weighted document score with a 95% bootstrap confidence "
                "interval and a binary verdict.",
    responses=_ERROR_RESPONSES,
)
def score(req: ScoreRequest) -> ScoreResponse:
    sents = split_sentences(req.text)
    if not sents:
        raise ApiError(
            422, "NO_SENTENCES_FOUND",
            "No sentences found. Paste at least one full English sentence "
            "and try again.",
        )
    if len(sents) > config.MAX_SENTENCES:
        raise ApiError(
            422, "TOO_MANY_SENTENCES",
            f"Text has {len(sents)} sentences; the limit is "
            f"{config.MAX_SENTENCES}. Shorten the passage and try again.",
        )

    try:
        detector, fallback_used = registry.resolve()
    except RuntimeError as exc:
        raise ApiError(503, "DETECTOR_UNAVAILABLE", str(exc)) from exc

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
            "The primary detection method was unavailable; results come "
            "from a fallback method instead."
        )

    return ScoreResponse(
        sentences=sentence_scores,
        document=DocumentScore(
            score=round(doc_score, 4),
            ci_low=round(ci_low, 4), ci_high=round(ci_high, 4),
            band=document_band(doc_score, [s.band for s in sentence_scores]),
            verdict=verdict_for(doc_score),
            confidence=round(confidence_for(doc_score), 4),
            word_count=total_words, sentence_count=len(sents),
        ),
        meta=Meta(
            method=detector.name, model_name=detector.model_name,
            version=detector.version, fallback_used=fallback_used,
            warnings=warnings,
        ),
    )
