"""Unit tests for src/documents/index.py, using a deterministic fake embedder."""
import zlib

from src.documents.index import VectorIndex

DIM = 64


def fake_embed(text: str) -> list[float]:
    """Bag-of-words hashed into a fixed-size vector: shared words → similar vectors."""
    vec = [0.0] * DIM
    for word in text.lower().split():
        vec[zlib.crc32(word.strip(".,?").encode()) % DIM] += 1.0
    return vec


def make_index() -> VectorIndex:
    return VectorIndex(
        embed_documents=lambda texts: [fake_embed(t) for t in texts],
        embed_query=fake_embed,
    )


TEXTS = [
    "consistent hashing ring keys nodes",
    "raft consensus leader election log replication",
    "http caching headers etag max age",
]


def test_empty_index_returns_nothing():
    assert make_index().search("anything") == []


def test_add_returns_count_and_grows():
    index = make_index()
    assert index.add(TEXTS) == 3
    assert len(index) == 3
    assert index.add(["one more text about queues"]) == 1
    assert len(index) == 4


def test_closest_chunk_comes_first():
    index = make_index()
    index.add(TEXTS)
    assert index.search("how does the raft leader election work", k=1) == [1]
    assert index.search("hashing ring", k=3)[0] == 0


def test_exclude_skips_used_chunks():
    index = make_index()
    index.add(TEXTS)
    results = index.search("hashing ring", k=2, exclude={0})
    assert 0 not in results
    assert len(results) == 2


def test_k_larger_than_index_returns_everything_not_excluded():
    index = make_index()
    index.add(TEXTS)
    assert sorted(index.search("anything", k=10, exclude={2})) == [0, 1]


def test_failed_embedding_adds_nothing():
    def broken(texts):
        raise RuntimeError("embedder down")

    index = VectorIndex(embed_documents=broken, embed_query=fake_embed)
    try:
        index.add(TEXTS)
    except RuntimeError:
        pass
    assert len(index) == 0
