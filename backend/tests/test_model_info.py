"""/model-info: the front end relies on this for input limits and an
'About the model' panel, so its shape and a few key values are pinned
here against the committed statistical_model.meta.json."""
import json
import os

from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"  # endpoint doesn't touch the detector

from app.main import app  # noqa: E402
from app.statistical_meta import META_PATH  # noqa: E402

client = TestClient(app)


def test_model_info_shape_and_limits():
    r = client.get("/api/v1/model-info")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "model_name", "version", "dataset", "metrics",
        "essay_level_metrics", "bands", "input_limits",
    }
    assert body["input_limits"] == {
        "min_text_chars": 20, "max_text_chars": 12_000, "max_sentences": 300,
    }
    assert body["bands"] == {"low_below": 0.35, "high_at_or_above": 0.65}


def test_model_info_matches_committed_meta_json():
    on_disk = json.loads(META_PATH.read_text())
    body = client.get("/api/v1/model-info").json()
    assert body["model_name"] == on_disk["model_name"]
    assert body["version"] == on_disk["version"]
    assert body["metrics"] == on_disk["metrics"]
