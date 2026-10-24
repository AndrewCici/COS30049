"""SHA-256 integrity check for the committed statistical-model artifact.

A corrupted download or a tampered binary would silently change every
prediction the app makes; refusing to start on a mismatch is safer than
serving from an unverified model file. `scripts/hash_model.py` regenerates
the recorded hash after a legitimate retrain.
"""
import hashlib
from pathlib import Path


class ModelIntegrityError(RuntimeError):
    """Raised when the model artifact is missing or does not match its hash."""


def verify_sha256(model_path: Path, hash_path: Path) -> None:
    if not model_path.exists():
        raise ModelIntegrityError(
            f"Model file not found: {model_path}. Run backend/ml/train.py "
            "or restore the committed artifact."
        )
    if not hash_path.exists():
        raise ModelIntegrityError(
            f"Hash file not found: {hash_path}. Run "
            "`python scripts/hash_model.py` to generate it."
        )
    expected = hash_path.read_text().split()[0].strip().lower()
    actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ModelIntegrityError(
            f"SHA-256 mismatch for {model_path}: expected {expected}, got "
            f"{actual}. The file may be corrupted or tampered with."
        )
