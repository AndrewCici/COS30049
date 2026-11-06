"""FastAPI application: the scoring endpoint, health probe and model info."""
import logging
import uuid
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Receive, Scope, Send

from . import config
from .aggregate import bootstrap_ci, document_band, weighted_mean
from .detectors import registry
from .detectors.base import Detector
from .model_integrity import ModelIntegrityError
from .normalise import normalise_text, translate_span
from .schemas import (BAND_THRESHOLDS, DocumentScore, ErrorResponse,
                      HealthResponse, InputLimits, Meta, ModelInfoResponse,
                      NormalisationInfo, ScoreRequest, ScoreResponse,
                      SentenceScore, band_for, confidence_for, verdict_for)
from .security.body_limit import BodySizeLimitMiddleware
from .security.headers import SecurityHeadersMiddleware, headers_for_path
from .security.limiter import InferenceUnavailableError, inference_limiter
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
    if not config.security_defences_enabled():
        logger.warning(
            "SECURITY_DEFENCES=off: body-size limit, sentence-count cap and "
            "the inference concurrency limiter are all DISABLED. For "
            "demonstrating the DoS attack scripts only; never run this in "
            "production."
        )
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
    # ReDoc duplicates Swagger UI (/docs) against the same OpenAPI document
    # and needs a third external origin (Google Fonts) the Content-Security-
    # Policy would otherwise never need to allow; disabled rather than
    # widened for a page nothing links to. See security/misconfig/FINDINGS.md.
    redoc_url=None,
)

# Registered innermost-first: add_middleware() builds a stack where the
# LAST one added is OUTERMOST (runs first on the way in, last on the way
# out). Desired order, outside in: security-headers -> request-id -> CORS ->
# body-size-limit -> router. Putting the body-size check inside CORS (not
# outside it) means a rejected oversized request still gets CORS headers on
# its 413 response, so a browser can actually read it instead of reporting
# an opaque network error; putting request-id and security-headers outside
# that means X-Request-ID and every security header land on that 413 too,
# and on every other response, without each inner layer needing to know
# about them. The one response this can't reach is a truly unhandled
# exception's 500 (Starlette's ServerErrorMiddleware sends that from
# outside all user middleware); unhandled_exception_handler below adds the
# same headers there by hand, exactly as it already does for CORS.
app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


class RequestIDMiddleware:
    """Tags every request/response with a UUID so a client-reported problem
    can be matched to the corresponding server-side log line. Pure ASGI (not
    BaseHTTPMiddleware) so it sets `scope["state"]` directly, and inner
    middleware -- notably BodySizeLimitMiddleware, which never gets to build
    a Starlette `Request` -- can read the same request_id."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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


def _validation_message(error: dict) -> str:
    """One plain-English sentence for the first Pydantic error.

    Pydantic's raw messages are written for developers ("String should have
    at least 20 characters", "Value error, ...") and, for a malformed body,
    name a byte offset instead of a field. The UI shows this text verbatim,
    so the common cases are rephrased; anything else falls back to
    Pydantic's own wording prefixed with the field name.
    """
    err_type = error.get("type", "")
    ctx = error.get("ctx") or {}
    field = ".".join(str(p) for p in error.get("loc", ()) if p != "body")

    if err_type == "json_invalid":
        return "The request body is not valid JSON."
    if err_type == "missing":
        return f"The '{field}' field is required."
    if err_type == "string_type":
        return f"The '{field}' field must be a string."
    if err_type == "string_too_short":
        return f"The text is too short: enter at least {ctx.get('min_length')} characters."
    if err_type == "string_too_long":
        return f"The text is too long: the limit is {ctx.get('max_length'):,} characters."
    if err_type == "value_error":
        # Our own validators raise ValueError with a finished sentence;
        # Pydantic prepends "Value error, " to it.
        return str(error.get("msg", "")).removeprefix("Value error, ")
    message = error.get("msg", "Invalid input.")
    return f"{field}: {message}" if field else message


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", _validation_message(exc.errors()[0]),
                            _request_id(request)),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = _request_id(request)
    # The traceback is logged server-side, keyed by request_id, and never
    # returned to the client.
    logger.exception("Unhandled error [request_id=%s]", request_id)
    # Starlette sends this response from its outermost error middleware,
    # which sits outside CORSMiddleware, SecurityHeadersMiddleware and
    # RequestIDMiddleware alike, so the CORS, security and request-id
    # headers are all added here by hand. Without the CORS header the
    # browser hides the body and the front end can only report a network
    # failure instead of this message; without the others, a 500 would be
    # the one response that silently skips headers every other one carries.
    headers = {"Vary": "Origin", "X-Request-ID": request_id}
    if request.headers.get("origin") == config.FRONTEND_ORIGIN:
        headers["Access-Control-Allow-Origin"] = config.FRONTEND_ORIGIN
    if config.security_defences_enabled():
        headers.update(headers_for_path(request.url.path))
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_ERROR", "An unexpected error occurred. Please try again.",
            request_id,
        ),
        headers=headers,
    )


def _error_example(code: str, message: str) -> dict:
    """OpenAPI example body in the shared error envelope."""
    return {"application/json": {"example": _error_body(
        code, message, "3f2b8c1e-6a4d-4e0f-9b7a-2c5d8e1f0a93")}}


_ERROR_RESPONSES = {
    413: {
        "model": ErrorResponse,
        "description": "Request body too large; rejected before it is read.",
        "content": _error_example(
            "PAYLOAD_TOO_LARGE", "Request body exceeds the 65536-byte limit."),
    },
    422: {
        "model": ErrorResponse,
        "description": "Invalid input: malformed JSON, missing or non-string "
                       "`text`, text outside the character limits, "
                       "whitespace only, no sentences, or too many sentences.",
        "content": _error_example(
            "VALIDATION_ERROR",
            "The text is too short: enter at least 20 characters."),
    },
    503: {
        "model": ErrorResponse,
        "description": "No detection method is available, or the server is "
                       "under heavy load (inference queue full or timed "
                       "out). Carries a Retry-After header when load is the "
                       "cause.",
        "content": _error_example(
            "INFERENCE_QUEUE_FULL",
            "The server is handling too many scoring requests right now. "
            "Try again shortly."),
    },
    500: {
        "model": ErrorResponse,
        "description": "Unexpected server error. Details are logged "
                       "server-side under the request_id, never returned.",
        "content": _error_example(
            "INTERNAL_ERROR", "An unexpected error occurred. Please try again."),
    },
}


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service and detector availability",
    description="Reports which detection method is currently active and "
                "which methods are available, without triggering a model "
                "download. Used to drive a status indicator in the UI. "
                "Defined as a plain `async def` and never touches the "
                "inference concurrency limiter, so it stays responsive even "
                "while /score is under heavy load.",
)
async def health() -> HealthResponse:
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


async def _run_inference(detector: Detector, texts: list[str]) -> list[float]:
    """Runs the (synchronous, CPU-bound) detector off the event loop, with a
    timeout as a backstop. The timeout bounds how long the caller waits, not
    how long the worker thread actually runs -- Python cannot forcibly kill a
    thread -- so `abandon_on_cancel` lets a timed-out call stop occupying a
    concurrency slot immediately rather than holding it hostage until the
    orphaned thread eventually finishes."""
    try:
        with anyio.fail_after(config.INFERENCE_TIMEOUT_S):
            return await anyio.to_thread.run_sync(
                detector.score_sentences, texts, abandon_on_cancel=True
            )
    except TimeoutError as exc:
        raise ApiError(
            503, "INFERENCE_TIMEOUT",
            "Scoring took too long and was aborted. Try a shorter passage.",
            headers={"Retry-After": "2"},
        ) from exc


@app.post(
    "/api/v1/score",
    response_model=ScoreResponse,
    tags=["Detection"],
    summary="Score a passage for AI-generated content",
    description="Splits the passage into sentences, scores each with the "
                "active detector, and aggregates them into a length-"
                "weighted document score with a 95% bootstrap confidence "
                "interval and a binary verdict. Under heavy concurrent load "
                "this may return 503 with a Retry-After header instead of "
                "queuing indefinitely (see security/dos/README.md).",
    responses=_ERROR_RESPONSES,
)
async def score(req: ScoreRequest) -> ScoreResponse:
    # Scoring and sentence-splitting run on normalised text (defeats
    # homoglyph/invisible-character/combining-mark evasion -- see
    # security/evasion/REPORT.md); `norm` stays available to translate
    # offsets back so the response highlights the user's own pasted text.
    norm = normalise_text(req.text) if config.normalise_input_enabled() else None
    working_text = norm.text if norm is not None else req.text

    sents = split_sentences(working_text)
    if not sents:
        raise ApiError(
            422, "NO_SENTENCES_FOUND",
            "No sentences found. Paste at least one full English sentence "
            "and try again.",
        )
    if config.security_defences_enabled() and len(sents) > config.MAX_SENTENCES:
        raise ApiError(
            422, "TOO_MANY_SENTENCES",
            f"Text has {len(sents)} sentences; the limit is "
            f"{config.MAX_SENTENCES}. Shorten the passage and try again.",
        )

    try:
        detector, fallback_used = registry.resolve()
    except RuntimeError as exc:
        raise ApiError(503, "DETECTOR_UNAVAILABLE", str(exc)) from exc

    try:
        async with inference_limiter.slot():
            raw_scores = await _run_inference(detector, [s.text for s in sents])
    except InferenceUnavailableError as exc:
        raise ApiError(
            503, "INFERENCE_QUEUE_FULL",
            "The server is handling too many scoring requests right now. "
            "Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_s)},
        ) from exc
    raw_scores = [min(max(s, 0.0), 1.0) for s in raw_scores]

    sentence_scores = []
    for s, score_i in zip(sents, raw_scores):
        if norm is not None:
            disp_start, disp_end = translate_span(norm, s.start, s.end)
            disp_text = req.text[disp_start:disp_end]
        else:
            disp_start, disp_end, disp_text = s.start, s.end, s.text
        sentence_scores.append(SentenceScore(
            text=disp_text, start=disp_start, end=disp_end,
            score=round(score_i, 4), band=band_for(score_i),
            word_count=s.word_count,
        ))

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
            normalisation=NormalisationInfo(
                applied=norm is not None,
                format_chars_removed=norm.cf_removed if norm else 0,
                combining_marks_removed=norm.combining_marks_removed if norm else 0,
                confusables_mapped=norm.confusables_mapped if norm else 0,
            ),
        ),
    )
