"""Extracts the pinned confusables subset baked into backend/app/normalise.py
from the official Unicode TR39 data file committed alongside this script
(confusables.txt, downloaded from https://www.unicode.org/Public/security/latest/confusables.txt,
dated 2026-08-06, UTS #39 version 18.0.0).

Run from this directory: python3 -I extract_confusables.py

This script is not imported by the application; it documents and
reproduces how the pinned table in normalise.py was derived, so the
mapping is independently verifiable against the source file rather than
hand-typed. Filters to confusables whose source is a Cyrillic or Greek
letter (the realistic homoglyph attack surface against English text) and
whose target is exactly one ASCII letter -- multi-character targets are
excluded to keep the defence's offset bookkeeping exact (one output
character per pinned-table substitution).
"""
import unicodedata


def extract() -> list[tuple[int, str, str]]:
    rows = []
    with open("confusables.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            if len(parts) < 2:
                continue
            try:
                src_cp = int(parts[0].strip(), 16)
                tgt_cps = [int(h, 16) for h in parts[1].strip().split()]
            except ValueError:
                continue
            if len(tgt_cps) != 1:
                continue
            tgt_cp = tgt_cps[0]
            if not (0x41 <= tgt_cp <= 0x5A or 0x61 <= tgt_cp <= 0x7A):
                continue
            if not (0x0370 <= src_cp <= 0x03FF or 0x0400 <= src_cp <= 0x04FF):
                continue
            rows.append((src_cp, chr(src_cp), chr(tgt_cp)))
    rows.sort()
    return rows


def close_under_nfkc(rows: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """normalise_text() runs NFKC *before* the confusables lookup (needed
    for fullwidth-form and Vietnamese-diacritic handling -- see
    backend/app/normalise.py's module docstring). That means a source
    character whose own NFKC form differs from itself is looked up by that
    *transformed* codepoint, not its original one. Found by testing this
    table against security/evasion/run_experiment.py: two entries --
    GREEK LUNATE SIGMA SYMBOL (U+03F2) and GREEK CAPITAL LUNATE SIGMA
    SYMBOL (U+03F9) -- NFKC-normalise to GREEK SMALL/CAPITAL LETTER FINAL
    SIGMA (U+03C2/U+03A3), which were missing their own entries, so those
    two characters survived normalisation unmapped. This closes the table
    under NFKC: for every entry whose source normalises to a different,
    not-yet-covered codepoint, that codepoint is added with the same
    target. Run to a fixed point (in practice one pass is enough; the
    loop guards against needing more)."""
    table = {cp: tgt for cp, _, tgt in rows}
    changed = True
    while changed:
        changed = False
        for cp in list(table):
            nfkc = unicodedata.normalize("NFKC", chr(cp))
            if len(nfkc) == 1 and ord(nfkc) != cp and ord(nfkc) not in table:
                table[ord(nfkc)] = table[cp]
                changed = True
    return sorted((cp, chr(cp), tgt) for cp, tgt in table.items())


if __name__ == "__main__":
    rows = close_under_nfkc(extract())
    for src_cp, src_ch, tgt_ch in rows:
        name = unicodedata.name(src_ch, "?")
        print(f"    {src_cp:#06x}: {tgt_ch!r},  # {name}")
    print(f"# {len(rows)} entries")
