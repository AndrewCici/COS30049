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
  register of model output;
- DiscourseFeatures (below) adds literature-motivated register, readability
  and informality signals that TF-IDF cannot express as a single number.
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


# ---------------------------------------------------------------------------
# Second feature family: register, readability and informality signals.
# Kept in its own transformer (not folded into StylometricFeatures) so that
# models trained before it existed still load, and so it can be ablated.
# Each feature states WHAT IT IS MEANT TO CAPTURE; these are hypotheses
# motivated by the stylometry / detection literature, not tuned on a score.
# ---------------------------------------------------------------------------
# Closed-class words (articles, prepositions, pronouns, auxiliaries,
# conjunctions). Their frequencies are largely topic-independent and have been
# a standard authorship-attribution signal since Mosteller & Wallace (1964).
_FUNCTION_WORDS = frozenset("""
a an the this that these those i me my mine we us our ours you your yours he him
his she her hers it its they them their theirs of in on at by for with about
against between into through during before after above below to from up down
out off over under again and but or nor so yet if because while although as
until than is am are was were be been being have has had having do does did
doing will would shall should can could may might must not no there here
""".split())

# Formal discourse connectives and "essay scaffolding" phrases. Hypothesis:
# instruction-tuned LLMs use them more evenly and more often than casual human
# writers. Phrase list is deliberately short and inspectable.
_CONNECTIVES = re.compile(
    r"\b(furthermore|moreover|additionally|in addition|overall|therefore|"
    r"consequently|thus|in conclusion|in summary|it is important to note|"
    r"it is worth noting|as a result|for instance|for example|in general|"
    r"on the other hand|ultimately|in essence)\b", re.IGNORECASE)

# Hedging / epistemic modality. Hypothesis: assistant-style answers hedge
# ("generally", "can", "may") instead of committing to a personal claim.
_HEDGES = frozenset("""may might could can generally typically often usually
sometimes possibly potentially likely various several""".split())

_SECOND_PERSON = frozenset({"you", "your", "yours", "yourself", "yourselves"})
_PASSIVE = re.compile(r"\b(am|is|are|was|were|be|been|being)\s+\w+(ed|en)\b",
                      re.IGNORECASE)
_REPEATED_PUNCT = re.compile(r"[!?]{2,}|\.{3,}")
_LOWER_I = re.compile(r"\bi\b")  # standalone lowercase "i"
_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def _syllables(word: str) -> int:
    """Rough syllable count (vowel groups, silent final e) for Flesch."""
    w = word.lower()
    n = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(n, 1)


class DiscourseFeatures(BaseEstimator, TransformerMixin):
    """Register / readability / informality features, each scaled to ~[0, 1]."""

    FEATURE_NAMES = [
        "function_word_rate",   # topic-independent syntactic style
        "connective_rate",      # formal discourse scaffolding
        "hedge_rate",           # epistemic hedging
        "second_person_rate",   # direct address to the reader
        "passive_rate",         # impersonal, formal register
        "long_word_rate",       # lexical sophistication (words >= 7 letters)
        "flesch_reading_ease",  # readability (Flesch, 1948), rescaled
        "starts_lowercase",     # informal / careless capitalisation
        "repeated_punct_rate",  # "!!", "??", "..." emphasis, typical of humans
        "lowercase_i_rate",     # "i" instead of "I", informal typing
    ]

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = []
        for text in X:
            words = _WORD.findall(text.lower())
            n = max(len(words), 1)
            n_sent = max(sum(text.count(c) for c in ".!?"), 1)
            syll = sum(_syllables(w) for w in words)
            flesch = 206.835 - 1.015 * (len(words) / n_sent) - 84.6 * (syll / n)
            first_alpha = next((c for c in text if c.isalpha()), "A")
            rows.append([
                sum(w in _FUNCTION_WORDS for w in words) / n,
                min(len(_CONNECTIVES.findall(text)) * 5.0 / n, 1.0),
                sum(w in _HEDGES for w in words) / n,
                sum(w in _SECOND_PERSON for w in words) / n,
                min(len(_PASSIVE.findall(text)) * 5.0 / n, 1.0),
                sum(len(w) >= 7 for w in words) / n,
                (min(max(flesch, -50.0), 120.0) + 50.0) / 170.0,
                float(first_alpha.islower()),
                min(len(_REPEATED_PUNCT.findall(text)), 3) / 3.0,
                min(len(_LOWER_I.findall(text)) * 10.0 / n, 1.0),
            ])
        return np.asarray(rows, dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.FEATURE_NAMES)
