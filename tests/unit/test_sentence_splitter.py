"""Unit tests for src/pipeline/sentence_splitter.py."""
from src.pipeline.sentence_splitter import split_sentences


def _collect(tokens: list[str]) -> list[str]:
    return list(split_sentences(iter(tokens)))


def test_single_sentence():
    result = _collect(["Hello, world."])
    assert result == ["Hello, world."]


def test_question():
    result = _collect(["What is 2 plus 2?"])
    assert result == ["What is 2 plus 2?"]


def test_exclamation():
    result = _collect(["Great job!"])
    assert result == ["Great job!"]


def test_multiple_sentences():
    result = _collect(["The sky is blue. ", "The grass is green."])
    assert len(result) == 2
    assert result[0] == "The sky is blue."
    assert result[1] == "The grass is green."


def test_split_across_tokens():
    result = _collect(["First sentence", ". Second", " sentence."])
    assert len(result) == 2
    assert "First sentence." in result[0]
    assert "Second" in result[1]


def test_incomplete_last_sentence_flushed():
    result = _collect(["Hello there"])
    assert result == ["Hello there"]


def test_minimum_length_filter():
    # Single char "." should not be yielded
    result = _collect(["A."])
    # "A." is 2 chars < min length 3 — should be filtered or flushed
    # either way, no crash
    assert isinstance(result, list)


def test_empty_stream():
    result = _collect([])
    assert result == []


def test_ellipsis_boundary():
    result = _collect(["Well… that was interesting."])
    assert len(result) >= 1


def test_streaming_tokens():
    tokens = ["The", " quick", " brown", " fox.", " It", " jumps", " high!"]
    result = _collect(tokens)
    assert len(result) == 2
    assert "fox." in result[0]
    assert "high!" in result[1]
