"""Unit tests for src/documents/chunking.py."""
from src.documents.chunking import chunk_text

SENTENCE = "Consistent hashing keeps most keys in place when a node joins the ring. "


def long_text(sentences: int = 80) -> str:
    return "".join(f"{i}: {SENTENCE}" for i in range(sentences)).strip()


def test_empty_text_has_no_chunks():
    assert chunk_text("   ") == []


def test_short_text_is_a_single_chunk():
    assert chunk_text("One short paragraph.") == ["One short paragraph."]


def test_chunks_respect_the_size_limit():
    chunks = chunk_text(long_text(), size=1200, overlap=200)
    assert len(chunks) > 1
    assert all(len(c) <= 1200 for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(long_text(), size=1200, overlap=200)
    for previous, current in zip(chunks, chunks[1:]):
        assert current[:40] in previous


def test_chunks_end_at_sentence_boundaries_when_possible():
    chunks = chunk_text(long_text(), size=1200, overlap=200)
    assert all(c.endswith(".") for c in chunks)


def test_paragraph_breaks_are_preferred():
    para = "A" * 500 + "."
    text = f"{para}\n\n{para}\n\n{para}"
    chunks = chunk_text(text, size=1200, overlap=200)
    assert chunks[0] == f"{para}\n\n{para}"


def test_no_text_is_lost():
    text = long_text()
    joined = " ".join(chunk_text(text, size=1200, overlap=200))
    for i in range(80):
        assert f"{i}: Consistent hashing" in joined


def test_unbroken_text_is_still_split():
    chunks = chunk_text("x" * 3000, size=1200, overlap=200)
    assert all(len(c) <= 1200 for c in chunks)
    assert len(chunks) >= 3
