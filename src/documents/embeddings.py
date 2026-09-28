"""
Embeddings — OpenAI `text-embedding-3-small` (research.md §10).

Batches of EMBED_BATCH_SIZE are sent up to EMBED_CONCURRENCY at a time, and the
results keep the input order. The model needs no task prefixes.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from src import config
from src.documents.errors import EmbeddingUnavailableError
from src.openai_client import describe_error, get_sync_client

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 256
EMBED_CONCURRENCY = 4

_UNAVAILABLE = "Reference files can't be indexed right now: the OpenAI service is unavailable."


def _embed(inputs: list[str]) -> list[list[float]]:
    try:
        response = get_sync_client().embeddings.create(model=config.OPENAI_EMBED_MODEL, input=inputs)
    except Exception as exc:
        logger.error("Embedding request failed: %s", describe_error(exc))
        raise EmbeddingUnavailableError(_UNAVAILABLE) from exc
    return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages for indexing, in parallel batches, preserving order."""
    batches = [texts[i:i + EMBED_BATCH_SIZE] for i in range(0, len(texts), EMBED_BATCH_SIZE)]
    if len(batches) <= 1:
        return _embed(batches[0]) if batches else []
    with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as pool:
        results = list(pool.map(_embed, batches))
    return [vector for batch in results for vector in batch]


def embed_query(text: str) -> list[float]:
    """Embed the text used to search the index."""
    return _embed([text])[0]
