"""Unit tests for the detection-evasion defence (app/normalise.py) and its
wiring into /api/v1/score (see security/evasion/REPORT.md)."""
import os
import unicodedata

import pytest
from fastapi.testclient import TestClient

os.environ["AIDETECT_METHOD"] = "mock"

from app.main import app  # noqa: E402
from app.normalise import normalise_text, translate_span  # noqa: E402

client = TestClient(app)


# --- Unit tests on normalise_text() / translate_span() --------------------

def test_fullwidth_collapses_via_nfkc():
    # U+FF21.. is the fullwidth Latin block; NFKC's compatibility
    # decomposition alone defeats it, with no entry needed in the
    # confusables table.
    result = normalise_text("ＡＢＣ")
    assert result.text == "ABC"
    assert result.confusables_mapped == 0


def test_invisible_format_characters_stripped():
    # Zero-width space (U+200B) and word joiner (U+2060), both category Cf,
    # inserted mid-word.
    result = normalise_text("hu​man wri⁠tten")
    assert result.text == "human written"
    assert result.cf_removed == 2


def test_confusable_homoglyphs_mapped_to_latin():
    # CYRILLIC CAPITAL LETTER A (U+0410) and CYRILLIC SMALL LETTER O
    # (U+043E), both visually identical to their Latin counterparts.
    result = normalise_text("Аbоver")
    assert result.text == "Abover"
    assert result.confusables_mapped == 2


def test_zalgo_combining_marks_stripped():
    # 8 stacked combining marks on one base character. NFKC itself
    # recomposes only the first (acute + e -> the precomposed "e"), since
    # Unicode's canonical composition algorithm blocks a starter from
    # composing with a mark once an earlier mark of the same class already
    # attached (confirmed empirically, not assumed); the defence's own
    # mark-stripping step then removes the remaining 7, leaving a single
    # precomposed character where there were 9 codepoints.
    base = "e"
    zalgo = base + "́̂̃̄̅̆̇̈"
    result = normalise_text(zalgo)
    assert result.text == "é"
    assert result.combining_marks_removed == 7


def test_vietnamese_precomposed_text_is_unaffected():
    # "Vietnamese is beautiful." with the standard precomposed diacritics
    # a real user would paste. The defence must not mangle this: zero
    # marks stripped, zero confusables mapped, text unchanged.
    text = "Tiếng Việt rất hay."
    result = normalise_text(text)
    assert result.text == text
    assert result.combining_marks_removed == 0
    assert result.confusables_mapped == 0


def test_vietnamese_decomposed_form_recomposes_losslessly():
    # The same sentence, but with every precomposed letter decomposed into
    # base + combining marks (NFD) -- i.e. typed or pasted from a source
    # that never recomposed it. NFKC must reassemble it before the
    # combining-mark strip runs, so the normalised text is character-for-
    # character identical to the precomposed original, with nothing
    # stripped as if it were an attack.
    precomposed = "Tiếng Việt rất hay."
    decomposed = unicodedata.normalize("NFD", precomposed)
    assert decomposed != precomposed  # the test is only meaningful if so
    result = normalise_text(decomposed)
    assert result.text == precomposed
    assert result.combining_marks_removed == 0


def test_translate_span_maps_back_to_original_text():
    original = "a​bc"  # zero-width space between 'a' and 'bc'
    result = normalise_text(original)
    assert result.text == "abc"
    # "abc"[0:1] == "a" came from original[0:1].
    assert translate_span(result, 0, 1) == (0, 1)
    # "abc"[1:3] == "bc" came from original[2:4] (around the stripped char).
    assert translate_span(result, 1, 3) == (2, 4)


def test_translate_span_empty_input():
    result = normalise_text("")
    assert translate_span(result, 0, 0) == (0, 0)


# --- API-level tests --------------------------------------------------------

CLEAN = "The weather report indicates a storm is approaching the coast."
# Same sentence with 6 Latin letters swapped for Cyrillic homoglyphs that
# render near-identically: T->Т (U+0422), e->е (U+0435, twice), a->а
# (U+0430, twice), o->о (U+043E). Chosen from the pinned table in
# app/normalise.py.
ATTACKED = (
    "Тhе wеather report indicates а storm is "
    "аpproaching the cоast."
)


def test_sentence_offsets_match_original_request_text():
    r = client.post("/api/v1/score", json={"text": ATTACKED})
    assert r.status_code == 200
    body = r.json()
    for s in body["sentences"]:
        assert ATTACKED[s["start"]:s["end"]] == s["text"]


def test_homoglyph_attack_defeated_by_normalisation():
    clean = client.post("/api/v1/score", json={"text": CLEAN}).json()
    attacked = client.post("/api/v1/score", json={"text": ATTACKED}).json()

    # Scores are identical: after normalisation both requests score the
    # exact same character sequence.
    assert clean["document"]["score"] == attacked["document"]["score"]
    assert attacked["meta"]["normalisation"]["applied"] is True
    assert attacked["meta"]["normalisation"]["confusables_mapped"] == 6

    # But the sentence text shown back is the user's own original
    # (attacked) text, not the normalised one -- it must still match what
    # they pasted, for highlighting to line up on screen.
    assert attacked["sentences"][0]["text"] == ATTACKED


def test_homoglyph_attack_defeated_against_the_real_statistical_model(monkeypatch):
    # The mock detector hashes exact text, so equality there is almost
    # definitional. Repeating the same comparison against the actual
    # shipped model proves the defence works on the real TF-IDF vocabulary
    # match, not just the test double.
    monkeypatch.setenv("AIDETECT_METHOD", "statistical")
    clean = client.post("/api/v1/score", json={"text": CLEAN}).json()
    attacked = client.post("/api/v1/score", json={"text": ATTACKED}).json()
    assert clean["document"]["score"] == pytest.approx(attacked["document"]["score"])
    assert clean["sentences"][0]["score"] == pytest.approx(attacked["sentences"][0]["score"])


def test_normalise_input_off_disables_the_defence(monkeypatch):
    monkeypatch.setenv("NORMALISE_INPUT", "off")
    r = client.post("/api/v1/score", json={"text": ATTACKED})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["normalisation"]["applied"] is False
    assert body["meta"]["normalisation"]["confusables_mapped"] == 0
    # With the defence off, the attacked text is scored byte-for-byte as
    # typed, so the response sentence is still an exact slice of it.
    assert ATTACKED[body["sentences"][0]["start"]:body["sentences"][0]["end"]] == \
        body["sentences"][0]["text"]
