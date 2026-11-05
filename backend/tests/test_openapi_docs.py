"""/docs must describe every endpoint with an example request (where the
endpoint takes a body) and an example response, including error responses."""
import os

from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.main import app  # noqa: E402

SPEC = TestClient(app).get("/openapi.json").json()


def _resolve(schema: dict) -> dict:
    ref = schema.get("$ref")
    if ref:
        return SPEC["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    return schema


def _has_example(response: dict) -> bool:
    media = response.get("content", {}).get("application/json", {})
    if "example" in media or "examples" in media:
        return True
    return "examples" in _resolve(media.get("schema", {}))


def test_every_operation_has_summary_description_and_examples():
    for path, ops in SPEC["paths"].items():
        for method, op in ops.items():
            where = f"{method.upper()} {path}"
            assert op.get("summary"), where
            assert op.get("description"), where
            for status, response in op["responses"].items():
                assert _has_example(response), f"{where} {status} has no example"
            if "requestBody" in op:
                assert _has_example(op["requestBody"]), f"{where} request has no example"
