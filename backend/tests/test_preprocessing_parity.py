"""Guards the invariant that training-time sentence segmentation
(backend/ml/train.py) is exactly what the API uses at inference time
(app.sentences.split_sentences). A silent drift here would mean the model's
decision boundary was learned on text shaped differently from what
production actually feeds it."""
import pytest

from app.sentences import split_sentences

# ml.train pulls in pandas (requirements-train.txt), which the default dev
# install (requirements-dev.txt) deliberately does not include; skip rather
# than force training dependencies onto every test run.
pytest.importorskip("pandas")
from ml.train import doc_sentences  # noqa: E402
import ml.train as train_module  # noqa: E402


def test_train_module_uses_the_same_splitter_as_inference():
    assert train_module.split_sentences is split_sentences


def test_casino_games_splits_into_two_sentences():
    sents = split_sentences("This is a casino. It has games.")
    assert [s.text for s in sents] == ["This is a casino.", "It has games."]


def test_doc_sentences_only_filters_what_split_sentences_already_produced():
    text = ("Hi. " + "word " * 130).strip() + "."
    raw_texts = {s.text for s in split_sentences(text)}
    for sent_text, _word_count in doc_sentences(text):
        assert sent_text in raw_texts
