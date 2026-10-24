"""Catastrophic/quadratic regex backtracking audit for the sentence
splitter. Every input here is at the API's MAX_TEXT_CHARS ceiling, shaped to
probe the worst case for each regex in app.sentences:

- a chain of known abbreviations, which never advances the splitter's
  `start` pointer (used to blow up _is_abbreviation's search window);
- a run of sentence-final punctuation with no whitespace anywhere (the
  splitter's boundary regex can never match, so re.finditer must retry a
  failed match at every character position).

Before the fix in app.sentences (possessive, bounded punctuation quantifier
+ a capped abbreviation lookback window), these took 340ms and 1.3s
respectively on a 12,000-char input; see the comments in that module."""
import time

from app.config import MAX_TEXT_CHARS
from app.sentences import split_sentences

BUDGET_S = 0.1  # the task's own ceiling: must finish in well under 100ms


def _time_it(text: str) -> float:
    t0 = time.perf_counter()
    split_sentences(text)
    return time.perf_counter() - t0


def test_chained_abbreviations_stay_fast():
    text = ("Dr. " * (MAX_TEXT_CHARS // 4))[:MAX_TEXT_CHARS]
    assert _time_it(text) < BUDGET_S


def test_chained_single_letter_initials_stay_fast():
    text = ("A. " * (MAX_TEXT_CHARS // 3))[:MAX_TEXT_CHARS]
    assert _time_it(text) < BUDGET_S


def test_whitespace_free_punctuation_run_stays_fast():
    text = ("!?." * (MAX_TEXT_CHARS // 3 + 1))[:MAX_TEXT_CHARS]
    assert _time_it(text) < BUDGET_S


def test_punctuation_run_with_closing_quotes_stays_fast():
    text = ("!?.\")" * (MAX_TEXT_CHARS // 5 + 1))[:MAX_TEXT_CHARS]
    assert _time_it(text) < BUDGET_S


def test_mixed_pathological_shapes_stay_fast():
    third = MAX_TEXT_CHARS // 3
    text = (("Dr. " * third) + ("!?." * third) + ("A. " * third))[:MAX_TEXT_CHARS]
    assert _time_it(text) < BUDGET_S
