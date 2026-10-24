"""Central, environment-overridable runtime configuration.

Every tunable the rest of the app reads lives here, next to its default and
the reasoning behind it, instead of being scattered across modules as bare
literals.
"""
import os


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value == "1"


# Character bounds on the raw request text. 12,000 chars (~2,000 words) is
# comfortably above a multi-paragraph essay while bounding sentence-splitting
# and bootstrap-CI cost (see security/dos/measure_cost.py); 20 chars is
# roughly the shortest input that can contain one real sentence.
MAX_TEXT_CHARS = _int_env("AIDETECT_MAX_TEXT_CHARS", 12_000)
MIN_TEXT_CHARS = _int_env("AIDETECT_MIN_TEXT_CHARS", 20)

# A pasted whole document can legitimately contain hundreds of sentences;
# beyond this, per-sentence scoring and the bootstrap CI stop being useful
# to a reader and start being expensive to compute.
MAX_SENTENCES = _int_env("AIDETECT_MAX_SENTENCES", 300)

# Origin the API accepts cross-origin requests from. A single explicit
# origin (not a wildcard or regex) keeps CORS from silently widening as new
# dev ports or deployments are added.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

# The HF transformer needs torch+transformers installed and downloads
# ~500MB of weights on first use; it is opt-in so the default install only
# needs requirements.txt and the committed statistical model. A function
# (not a frozen constant) so tests can toggle it per-case, the same way the
# existing AIDETECT_METHOD / AIDETECT_ALLOW_MOCK switches are read live.
def enable_hf() -> bool:
    return _bool_env("AIDETECT_ENABLE_HF")
