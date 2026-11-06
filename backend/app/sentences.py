"""Sentence segmentation with character offsets.

A small rule-based splitter is used instead of an NLP dependency (nltk/spacy)
so segmentation works offline, is deterministic, and — critically — never
changes when the detection model is swapped. Offsets into the *original*
text are preserved so the frontend can highlight sentences in place.
"""
import re
from dataclasses import dataclass

# Common abbreviations that end with a period but do not end a sentence.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g",
    "i.e", "fig", "al", "inc", "ltd", "co", "corp", "dept", "est", "approx",
    "no", "vol", "pp", "ed", "eds", "univ", "assn", "bros", "ph.d", "u.s",
    "u.k", "a.m", "p.m", "jan", "feb", "mar", "apr", "jun", "jul", "aug",
    "sep", "sept", "oct", "nov", "dec", "mon", "tue", "wed", "thu", "fri",
    "sat", "sun",
}

# Candidate boundary: sentence-final punctuation (with optional closing
# quotes/brackets) followed by whitespace, or a newline acting as a break.
#
# The punctuation run is a POSSESSIVE, BOUNDED quantifier (`{1,20}+`, Python
# 3.11+), not a plain `+`, for two compounding reasons:
# - Possessive: once `[.!?]{1,20}+` has greedily consumed a run, every
#   character in that run is -- by construction -- followed only by more
#   punctuation, never whitespace, so backtracking it character-by-character
#   to retry `(\s+)` at an earlier offset can never succeed. Plain `+` still
#   tries every one of those doomed retries: O(n) wasted work per failed
#   match attempt.
# - Bounded to 20: on input that is mostly unbroken punctuation with no
#   whitespace at all (e.g. "!?." repeated), `finditer` must still retry a
#   failed match at every one of the n starting positions; an unbounded
#   quantifier makes each of those retries itself O(n) (it possessively
#   consumes all the way to the end before failing), so the total stays
#   O(n^2). Capping the run length bounds each retry's cost to O(1)
#   instead, making the whole scan O(n). No real sentence boundary has
#   anywhere near 20 consecutive punctuation marks, so this never affects
#   legitimate text. Measured on a 12,000-char adversarial input: >1.3s
#   with plain `+`, ~70ms with only possessive, <2ms with both.
_BOUNDARY = re.compile(r'([.!?]{1,20}+[\'")\]]*)(\s+)|(\n{2,})')

_WORD = re.compile(r"[A-Za-z0-9''-]+")

# Any real abbreviation ("U.S.A.", "Ph.D", "approx") is well under this many
# characters; capping the lookback window keeps _is_abbreviation's cost
# constant per boundary instead of growing with how far back the current
# sentence started -- see the comment in split_sentences below.
_ABBREVIATION_LOOKBACK = 24


@dataclass
class Sentence:
    text: str
    start: int
    end: int

    @property
    def word_count(self) -> int:
        return len(_WORD.findall(self.text))


def _is_abbreviation(text_before: str) -> bool:
    """Check whether the token preceding a period is a known abbreviation
    or a single initial (as in 'J. Smith')."""
    m = re.search(r"([A-Za-z][A-Za-z.]*)\.$", text_before)
    if not m:
        return False
    token = m.group(1).lower().rstrip(".")
    return token in _ABBREVIATIONS or len(token) == 1


def _looks_like_number_context(text: str, dot_index: int) -> bool:
    """True for decimal points like '3.14'."""
    return (
        0 < dot_index < len(text) - 1
        and text[dot_index - 1].isdigit()
        and text[dot_index + 1].isdigit()
    )


def split_sentences(text: str) -> list[Sentence]:
    """Split text into sentences, keeping (start, end) offsets into `text`."""
    sentences: list[Sentence] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end(1) if m.group(1) else m.start(3)
        if m.group(1):
            # A chain of consecutive abbreviations ("Dr. Mr. Ms. ...") never
            # advances `start`, so text[start:m.end(1)] would otherwise grow
            # with every match and make both this slice and the regex search
            # inside _is_abbreviation O(n) each -- O(n^2) across the whole
            # input (measured: 340ms on 12,000 chars of "Dr. " unbounded,
            # versus under a millisecond bounded). Only the token right
            # before the period can ever matter, so the window is capped.
            before = text[max(start, m.end(1) - _ABBREVIATION_LOOKBACK):m.end(1)]
            last_dot = m.start(1)
            if _is_abbreviation(before.rstrip("'\")]")):
                continue
            if "." in m.group(1) and _looks_like_number_context(text, last_dot):
                continue
        chunk = text[start:end].strip()
        if chunk:
            s_off = start + (len(text[start:end]) - len(text[start:end].lstrip()))
            sentences.append(Sentence(text=chunk, start=s_off, end=s_off + len(chunk)))
        start = m.end()
    tail = text[start:].strip()
    if tail:
        s_off = start + (len(text[start:]) - len(text[start:].lstrip()))
        sentences.append(Sentence(text=tail, start=s_off, end=s_off + len(tail)))
    # Merge fragments with no words (e.g. stray punctuation) into neighbours.
    return [s for s in sentences if s.word_count > 0]
