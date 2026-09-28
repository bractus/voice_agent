"""
In-memory vector index over reference-material chunks (research.md §2).

A thin wrapper around faiss.IndexFlatIP with L2-normalised vectors, so the
inner-product score is cosine similarity. Row i of the index is chunk id i.
The embedding functions are passed in, so tests can use a fake embedder.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

import faiss
import numpy as np

EmbedDocuments = Callable[[list[str]], list[list[float]]]
EmbedQuery = Callable[[str], list[float]]


def _as_normalised(vectors: list[list[float]]) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    faiss.normalize_L2(array)
    return array


class VectorIndex:
    def __init__(self, embed_documents: EmbedDocuments, embed_query: EmbedQuery) -> None:
        self._embed_documents = embed_documents
        self._embed_query = embed_query
        self._index: faiss.IndexFlatIP | None = None

    def __len__(self) -> int:
        return 0 if self._index is None else self._index.ntotal

    def add(self, texts: list[str]) -> int:
        """
        Embed and add `texts`; their ids continue from the current size.

        Embedding happens before anything is added, so a failed embedding
        call leaves the index unchanged. Returns the number of texts added.
        """
        if not texts:
            return 0
        vectors = _as_normalised(self._embed_documents(texts))
        if self._index is None:
            self._index = faiss.IndexFlatIP(vectors.shape[1])
        self._index.add(vectors)
        return len(texts)

    def search(self, query: str, k: int = 4, exclude: Iterable[int] = ()) -> list[int]:
        """Return up to `k` chunk ids, best match first, skipping ids in `exclude`."""
        if not len(self):
            return []
        excluded = set(exclude)
        candidates = min(len(self), k + len(excluded))
        query_vector = _as_normalised([self._embed_query(query)])
        _, ids = self._index.search(query_vector, candidates)
        results = [int(i) for i in ids[0] if i != -1 and int(i) not in excluded]
        return results[:k]


def default_index() -> VectorIndex:
    """A VectorIndex backed by the OpenAI embedding model."""
    from src.documents import embeddings

    # Looked up at call time, so tests can patch the module's functions.
    return VectorIndex(
        embed_documents=lambda texts: embeddings.embed_documents(texts),
        embed_query=lambda text: embeddings.embed_query(text),
    )
