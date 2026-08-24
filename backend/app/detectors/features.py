"""Feature extraction shared by training (ml/train.py) and inference
(StatisticalDetector). Living in the app package guarantees the exact same
code runs at train and serve time, and keeps the joblib artifact loadable
(sklearn pickles reference this module path).

Feature rationale (what actually separates human from LLM prose):
- word/char TF-IDF n-grams capture lexical fingerprints — LLM text
  over-uses certain connectives ("furthermore", "overall", "it is
  important to note") and produces fewer typos/slang;
- stylometric numbers capture *burstiness*: human sentences vary more in
  length and vocabulary, use more punctuation variety, first-person
  pronouns, digits and contractions than the typically smooth, uniform
  register of model output.
"""
import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

_WORD = re.compile(r"[A-Za-z]+")
_FIRST_PERSON = {"i", "me", "my", "mine", "we", "us", "our", "ours", "i'm", "i've", "i'd"}
_CONTRACTION = re.compile(r"\b\w+'(s|t|re|ve|ll|d|m)\b", re.IGNORECASE)


class StylometricFeatures(BaseEstimator, TransformerMixin):
    """Per-text numeric style features, scaled to comparable ranges."""

    FEATURE_NAMES = [
        "n_words", "avg_word_len", "type_token_ratio", "punct_rate",
        "comma_rate", "digit_rate", "upper_rate", "first_person_rate",
        "contraction_rate", "word_len_std",
    ]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for text in X:
            words = _WORD.findall(text.lower())
            n_words = len(words)
            n_chars = max(len(text), 1)
            word_lens = [len(w) for w in words] or [0]
            rows.append([
                min(n_words, 200) / 200.0,
                float(np.mean(word_lens)) / 10.0,
                len(set(words)) / max(n_words, 1),
                sum(c in ".,;:!?—–-()\"'" for c in text) / n_chars,
                text.count(",") / max(n_words, 1),
                sum(c.isdigit() for c in text) / n_chars,
                sum(c.isupper() for c in text) / n_chars,
                sum(w in _FIRST_PERSON for w in words) / max(n_words, 1),
                len(_CONTRACTION.findall(text)) / max(n_words, 1),
                float(np.std(word_lens)) / 5.0,
            ])
        return np.asarray(rows, dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.FEATURE_NAMES)
