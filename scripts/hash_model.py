#!/usr/bin/env python3
"""Regenerate backend/models/statistical_model.sha256.

Run this after any legitimate change to statistical_model.joblib (normally:
after `python -m ml.train` retrains it). The backend verifies this hash at
startup and refuses to serve requests if it does not match (see
backend/app/model_integrity.py), so the new hash must be committed together
with the new model file.

Usage (from the repository root):
    python scripts/hash_model.py
"""
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "backend" / "models" / "statistical_model.joblib"
HASH_PATH = REPO_ROOT / "backend" / "models" / "statistical_model.sha256"


def main() -> None:
    if not MODEL_PATH.exists():
        sys.exit(f"{MODEL_PATH} does not exist.")
    digest = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    HASH_PATH.write_text(f"{digest}  {MODEL_PATH.name}\n")
    print(f"Wrote {HASH_PATH}: {digest}")


if __name__ == "__main__":
    main()
