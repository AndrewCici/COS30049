#!/usr/bin/env python3
"""Reproducible Unicode-based evasion perturbations (Section 2.8, see
security/evasion/REPORT.md). Each technique targets a different part of
the normalisation defence in backend/app/normalise.py:

- **homoglyph** — swaps a Latin letter for a Cyrillic/Greek look-alike,
  drawn from the exact pinned confusables table the defence checks
  against (deliberately: this experiment measures how well the defence
  covers the attack surface it claims to cover, not an attack built to
  evade it by construction).
- **invisible** — inserts a zero-width/format character (category Cf)
  after a letter or digit.
- **fullwidth** — replaces an ASCII printable character with its
  fullwidth Unicode compatibility form.
- **combining** — appends an extra combining diacritic (category Mn) to a
  letter, Zalgo-style.
- **mixed** — all four of the above, applied in sequence, each
  independently at the same rate.

`rate` is the per-eligible-character probability of perturbation, in
[0, 1]. `perturb()` is deterministic given (text, technique, rate, seed):
the same call always produces the same output, so an experiment run is
reproducible from its recorded seeds.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.normalise import _CONFUSABLES  # noqa: E402

# Latin letter -> every Cyrillic/Greek codepoint the defence's pinned
# table maps back to that letter.
_REVERSE_CONFUSABLES: dict[str, list[str]] = {}
for _src_cp, _tgt in _CONFUSABLES.items():
    _REVERSE_CONFUSABLES.setdefault(_tgt, []).append(chr(_src_cp))

# Zero-width space, zero-width non-joiner, zero-width joiner, word joiner:
# all category Cf, all invisible in a rendered browser/editor.
_INVISIBLE_CHARS = ["​", "‌", "‍", "⁠"]

# A handful of common combining diacritics (category Mn), the building
# blocks of "Zalgo" text.
_COMBINING_MARKS = ["́", "̀", "̂", "̃", "̄",
                    "̆", "̇", "̈"]

# Shifts ASCII 0x21 ('!') .. 0x7E ('~') into the Unicode fullwidth block
# (U+FF01 .. U+FF5E); NFKC's compatibility decomposition maps it straight
# back, which is exactly what this technique tries to get past.
_FULLWIDTH_OFFSET = 0xFF00 - 0x0020


def _to_fullwidth(ch: str) -> str | None:
    if "!" <= ch <= "~":
        return chr(ord(ch) + _FULLWIDTH_OFFSET)
    return None


def perturb_homoglyph(text: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        candidates = _REVERSE_CONFUSABLES.get(ch)
        out.append(rng.choice(candidates) if candidates and rng.random() < rate else ch)
    return "".join(out)


def perturb_invisible(text: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        out.append(ch)
        if ch.isalnum() and rng.random() < rate:
            out.append(rng.choice(_INVISIBLE_CHARS))
    return "".join(out)


def perturb_fullwidth(text: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        fw = _to_fullwidth(ch)
        out.append(fw if fw and rng.random() < rate else ch)
    return "".join(out)


def perturb_combining(text: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        out.append(ch)
        if ch.isalpha() and rng.random() < rate:
            out.append(rng.choice(_COMBINING_MARKS))
    return "".join(out)


def perturb_mixed(text: str, rate: float, rng: random.Random) -> str:
    text = perturb_homoglyph(text, rate, rng)
    text = perturb_invisible(text, rate, rng)
    text = perturb_fullwidth(text, rate, rng)
    text = perturb_combining(text, rate, rng)
    return text


TECHNIQUES = {
    "homoglyph": perturb_homoglyph,
    "invisible": perturb_invisible,
    "fullwidth": perturb_fullwidth,
    "combining": perturb_combining,
    "mixed": perturb_mixed,
}


def perturb(text: str, technique: str, rate: float, seed: int) -> str:
    return TECHNIQUES[technique](text, rate, random.Random(seed))


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text")
    ap.add_argument("--technique", choices=sorted(TECHNIQUES), default="homoglyph")
    ap.add_argument("--rate", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    out = perturb(args.text, args.technique, args.rate, args.seed)
    print(out)
    print("repr:", repr(out))


if __name__ == "__main__":
    main()
