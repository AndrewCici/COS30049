"""Unicode-based detection-evasion defence (Section 2.8, see
security/evasion/REPORT.md).

Three independent tricks let an attacker change how a passage *looks* to
the statistical model's tokeniser while leaving it visually identical (or
near enough) to a human reader, which is exactly what makes them evasion
rather than legitimate text variation:

- **Invisible format characters** (zero-width space/joiner, bidi controls,
  word joiner, soft hyphen -- Unicode category Cf) inserted inside or
  between words, splitting tokens the model was trained on without
  changing what renders on screen.
- **Homoglyphs** -- Cyrillic or Greek letters that render identically (or
  near-identically) to a Latin letter in most fonts, substituted for the
  genuine Latin letter the model's TF-IDF vocabulary was built from.
- **Combining-mark stacking** ("Zalgo" text) -- extra combining diacritics
  (category Mn/Mc/Me) piled onto a base character, again invisible-ish on
  screen but corrupting the exact character sequence the model tokenises.
  Fullwidth-form substitution (e.g. "A" U+FF21) is a fourth trick, but it
  needs no bespoke handling here: NFKC's own compatibility decomposition
  already defeats it (see below).

The defence runs `unicodedata.normalize("NFKC", ...)` first, then strips
any Cf and combining-mark characters NFKC did not resolve, then maps a
pinned subset of confusable characters back to their Latin skeleton. NFKC
is run first deliberately: besides collapsing fullwidth forms, it also
*recomposes* a legitimately decomposed accented letter (base + combining
marks typed or pasted as separate codepoints) back into its single
precomposed form wherever Unicode defines one -- which it does for every
Vietnamese diacritic combination this project tested against (see the
"Vietnamese diacritics" cost check in security/evasion/REPORT.md). Only
combining marks NFKC could *not* reattach this way survive to the
stripping step, which in practice means adversarial stacking, not normal
orthography.
"""
import unicodedata
from dataclasses import dataclass, field

# Cyrillic and Greek letters that are visually confusable with a single
# Latin ASCII letter -- the realistic homoglyph attack surface against
# English text. This is a PINNED SUBSET of the official Unicode TR39
# confusables data (security/evasion/data/confusables.txt, downloaded
# 2026-11-06, UTS #39 version 18.0.0), filtered by
# security/evasion/data/extract_confusables.py to confusables.txt entries
# whose source is in the Cyrillic (U+0400-04FF) or Greek (U+0370-03FF)
# block and whose target is exactly one ASCII letter, then CLOSED UNDER
# NFKC (see that script's close_under_nfkc): because normalise_text() runs
# NFKC before this lookup, a source character whose own NFKC form differs
# from itself (two of the 70 directly-filtered entries do) must also have
# an entry for that transformed codepoint, or it survives unmapped. This
# was found empirically running security/evasion/run_experiment.py against
# an earlier, un-closed version of this table, which showed a small
# nonzero residual success rate for the homoglyph attack that should have
# been exactly zero -- see security/evasion/REPORT.md. Re-run that script
# against the committed data file to reproduce this table exactly; it is
# not derived from memory.
_CONFUSABLES: dict[int, str] = {
    0x037f: 'J',  # GREEK CAPITAL LETTER YOT
    0x0391: 'A',  # GREEK CAPITAL LETTER ALPHA
    0x0392: 'B',  # GREEK CAPITAL LETTER BETA
    0x0395: 'E',  # GREEK CAPITAL LETTER EPSILON
    0x0396: 'Z',  # GREEK CAPITAL LETTER ZETA
    0x0397: 'H',  # GREEK CAPITAL LETTER ETA
    0x0399: 'l',  # GREEK CAPITAL LETTER IOTA
    0x039a: 'K',  # GREEK CAPITAL LETTER KAPPA
    0x039c: 'M',  # GREEK CAPITAL LETTER MU
    0x039d: 'N',  # GREEK CAPITAL LETTER NU
    0x039f: 'O',  # GREEK CAPITAL LETTER OMICRON
    0x03a1: 'P',  # GREEK CAPITAL LETTER RHO
    0x03a3: 'C',  # GREEK CAPITAL LETTER SIGMA (added for NFKC closure)
    0x03a4: 'T',  # GREEK CAPITAL LETTER TAU
    0x03a5: 'Y',  # GREEK CAPITAL LETTER UPSILON
    0x03a7: 'X',  # GREEK CAPITAL LETTER CHI
    0x03b1: 'a',  # GREEK SMALL LETTER ALPHA
    0x03b3: 'y',  # GREEK SMALL LETTER GAMMA
    0x03b9: 'i',  # GREEK SMALL LETTER IOTA
    0x03bd: 'v',  # GREEK SMALL LETTER NU
    0x03bf: 'o',  # GREEK SMALL LETTER OMICRON
    0x03c1: 'p',  # GREEK SMALL LETTER RHO
    0x03c2: 'c',  # GREEK SMALL LETTER FINAL SIGMA (added for NFKC closure)
    0x03c3: 'o',  # GREEK SMALL LETTER SIGMA
    0x03c5: 'u',  # GREEK SMALL LETTER UPSILON
    0x03d2: 'Y',  # GREEK UPSILON WITH HOOK SYMBOL
    0x03dc: 'F',  # GREEK LETTER DIGAMMA
    0x03ed: 'o',  # COPTIC SMALL LETTER SHIMA
    0x03f1: 'p',  # GREEK RHO SYMBOL
    0x03f2: 'c',  # GREEK LUNATE SIGMA SYMBOL
    0x03f3: 'j',  # GREEK LETTER YOT
    0x03f8: 'p',  # GREEK SMALL LETTER SHO
    0x03f9: 'C',  # GREEK CAPITAL LUNATE SIGMA SYMBOL
    0x03fa: 'M',  # GREEK CAPITAL LETTER SAN
    0x0405: 'S',  # CYRILLIC CAPITAL LETTER DZE
    0x0406: 'l',  # CYRILLIC CAPITAL LETTER BYELORUSSIAN-UKRAINIAN I
    0x0408: 'J',  # CYRILLIC CAPITAL LETTER JE
    0x0410: 'A',  # CYRILLIC CAPITAL LETTER A
    0x0412: 'B',  # CYRILLIC CAPITAL LETTER VE
    0x0415: 'E',  # CYRILLIC CAPITAL LETTER IE
    0x041a: 'K',  # CYRILLIC CAPITAL LETTER KA
    0x041c: 'M',  # CYRILLIC CAPITAL LETTER EM
    0x041d: 'H',  # CYRILLIC CAPITAL LETTER EN
    0x041e: 'O',  # CYRILLIC CAPITAL LETTER O
    0x0420: 'P',  # CYRILLIC CAPITAL LETTER ER
    0x0421: 'C',  # CYRILLIC CAPITAL LETTER ES
    0x0422: 'T',  # CYRILLIC CAPITAL LETTER TE
    0x0423: 'Y',  # CYRILLIC CAPITAL LETTER U
    0x0425: 'X',  # CYRILLIC CAPITAL LETTER HA
    0x042c: 'b',  # CYRILLIC CAPITAL LETTER SOFT SIGN
    0x0430: 'a',  # CYRILLIC SMALL LETTER A
    0x0433: 'r',  # CYRILLIC SMALL LETTER GHE
    0x0435: 'e',  # CYRILLIC SMALL LETTER IE
    0x043e: 'o',  # CYRILLIC SMALL LETTER O
    0x0440: 'p',  # CYRILLIC SMALL LETTER ER
    0x0441: 'c',  # CYRILLIC SMALL LETTER ES
    0x0443: 'y',  # CYRILLIC SMALL LETTER U
    0x0445: 'x',  # CYRILLIC SMALL LETTER HA
    0x0448: 'w',  # CYRILLIC SMALL LETTER SHA
    0x0455: 's',  # CYRILLIC SMALL LETTER DZE
    0x0456: 'i',  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
    0x0458: 'j',  # CYRILLIC SMALL LETTER JE
    0x0461: 'w',  # CYRILLIC SMALL LETTER OMEGA
    0x0474: 'V',  # CYRILLIC CAPITAL LETTER IZHITSA
    0x0475: 'v',  # CYRILLIC SMALL LETTER IZHITSA
    0x04ae: 'Y',  # CYRILLIC CAPITAL LETTER STRAIGHT U
    0x04af: 'y',  # CYRILLIC SMALL LETTER STRAIGHT U
    0x04ba: 'h',  # CYRILLIC CAPITAL LETTER SHHA
    0x04bb: 'h',  # CYRILLIC SMALL LETTER SHHA
    0x04bd: 'e',  # CYRILLIC SMALL LETTER ABKHASIAN CHE
    0x04c0: 'l',  # CYRILLIC LETTER PALOCHKA
    0x04cf: 'l',  # CYRILLIC SMALL LETTER PALOCHKA
}

_MARK_CATEGORIES = frozenset({"Mn", "Mc", "Me"})


@dataclass
class NormaliseResult:
    text: str
    # offset_map[i] = (start, end) span in the ORIGINAL text that produced
    # output character i, so a (start, end) span in `text` can be mapped
    # back to the span of original text it came from (see translate_span).
    offset_map: list[tuple[int, int]] = field(default_factory=list)
    original_length: int = 0
    cf_removed: int = 0
    combining_marks_removed: int = 0
    confusables_mapped: int = 0


def _clusters(text: str):
    """Yields (start, end) spans over `text`: each is either one Cf
    (invisible format) character alone, or one base character plus any
    combining marks immediately following it. This is the unit Unicode
    canonical composition (used by NFKC) itself operates over, so
    normalising one cluster in isolation matches normalising the whole
    string -- while letting each output character keep a precise pointer
    back to the span of original text it came from."""
    i, n = 0, len(text)
    while i < n:
        if unicodedata.category(text[i]) == "Cf":
            yield (i, i + 1)
            i += 1
            continue
        j = i + 1
        while j < n and unicodedata.category(text[j]) in _MARK_CATEGORIES:
            j += 1
        yield (i, j)
        i = j


def _process_cluster(cluster: str) -> tuple[str, int, int, int]:
    nfkc = unicodedata.normalize("NFKC", cluster)
    out: list[str] = []
    cf_removed = marks_removed = confusables_mapped = 0
    for ch in nfkc:
        category = unicodedata.category(ch)
        if category == "Cf":
            cf_removed += 1
            continue
        if category in _MARK_CATEGORIES:
            marks_removed += 1
            continue
        replacement = _CONFUSABLES.get(ord(ch))
        if replacement is not None:
            confusables_mapped += 1
            out.append(replacement)
        else:
            out.append(ch)
    return "".join(out), cf_removed, marks_removed, confusables_mapped


def normalise_text(text: str) -> NormaliseResult:
    """Normalises `text` for scoring while keeping every output character
    traceable back to the original text it came from."""
    out_parts: list[str] = []
    offset_map: list[tuple[int, int]] = []
    cf_total = marks_total = confusables_total = 0
    for start, end in _clusters(text):
        out, cf_n, marks_n, confusables_n = _process_cluster(text[start:end])
        cf_total += cf_n
        marks_total += marks_n
        confusables_total += confusables_n
        out_parts.append(out)
        offset_map.extend([(start, end)] * len(out))
    return NormaliseResult(
        text="".join(out_parts),
        offset_map=offset_map,
        original_length=len(text),
        cf_removed=cf_total,
        combining_marks_removed=marks_total,
        confusables_mapped=confusables_total,
    )


def translate_span(result: NormaliseResult, start: int, end: int) -> tuple[int, int]:
    """Maps a (start, end) span over `result.text` back to the (start, end)
    span of the original text it was produced from."""
    n = len(result.offset_map)
    if n == 0 or start >= n:
        return (result.original_length, result.original_length)
    orig_start = result.offset_map[start][0]
    if end <= start:
        return (orig_start, orig_start)
    orig_end = result.offset_map[min(end, n) - 1][1]
    return (orig_start, orig_end)
