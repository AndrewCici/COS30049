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
_BOUNDARY = re.compile(r'([.!?]+[\'")\]]*)(\s+)|(\n{2,})')

_WORD = re.compile(r"[A-Za-z0-9''-]+")


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
            before = text[start:m.end(1)]
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
