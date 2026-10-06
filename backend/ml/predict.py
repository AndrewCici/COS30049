"""Score text with the trained detector from the command line.

Usage (from backend/):
    python -m ml.predict "First sentence here. Second sentence here."
    python -m ml.predict --file essay.txt

Prints one probability per sentence (probability the sentence is AI-generated)
and a document score. The document score is the word-count-weighted mean of
the sentence probabilities, the same rule the web app uses. (The web app also
adds a bootstrap confidence interval; see app/aggregate.py.)
"""
import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import joblib  # noqa: E402

from app.sentences import split_sentences  # noqa: E402

MODELS = BACKEND / "models"


def load_model():
    """Prefer the model produced by ml.train; fall back to the legacy name."""
    for name in ("final_model.pkl", "statistical_model.joblib"):
        if (MODELS / name).exists():
            return joblib.load(MODELS / name), name
    sys.exit("No trained model found in models/. Run `python -m ml.train` first.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text", nargs="?", help="text to score (or use --file)")
    ap.add_argument("--file", help="read the text from this file instead")
    args = ap.parse_args()
    text = Path(args.file).read_text() if args.file else args.text
    if not text:
        ap.error("give some text or --file")

    model, name = load_model()
    sentences = split_sentences(text)
    if not sentences:
        sys.exit("No sentences found.")
    probs = model.predict_proba([s.text for s in sentences])[:, 1]
    weights = [max(s.word_count, 1) for s in sentences]
    doc_score = sum(p * w for p, w in zip(probs, weights)) / sum(weights)

    print(f"model: {name}")
    for s, p in zip(sentences, probs):
        print(f"  {p:.3f}  {s.text}")
    print(f"document AI-likelihood: {doc_score:.3f}  ({len(sentences)} sentences)")


if __name__ == "__main__":
    main()
