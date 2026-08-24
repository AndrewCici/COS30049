from app.sentences import split_sentences


def test_basic_split():
    sents = split_sentences("First sentence here. Second sentence there.")
    assert [s.text for s in sents] == ["First sentence here.", "Second sentence there."]


def test_offsets_match_original():
    text = "  Hello world today. And another one!  "
    for s in split_sentences(text):
        assert text[s.start:s.end] == s.text


def test_abbreviations_not_split():
    sents = split_sentences("Dr. Smith met Mr. Jones yesterday. They talked.")
    assert len(sents) == 2
    assert sents[0].text.startswith("Dr. Smith")


def test_decimal_numbers_not_split():
    sents = split_sentences("The value of pi is 3.14 exactly. Everyone knows that.")
    assert len(sents) == 2


def test_question_and_exclamation():
    sents = split_sentences("Is this real? Yes it is! Good news then.")
    assert len(sents) == 3


def test_empty_and_whitespace():
    assert split_sentences("") == []
    assert split_sentences("   \n\n  ") == []


def test_no_terminal_punctuation():
    sents = split_sentences("a passage with no final period at all")
    assert len(sents) == 1


def test_word_count():
    (s,) = split_sentences("Three little words.")
    assert s.word_count == 3
