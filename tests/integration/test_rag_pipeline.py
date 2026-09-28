"""
Integration test for reference-material retrieval with the real OpenAI
embedding model (text-embedding-3-small). Skipped without OPENAI_API_KEY.
"""
from pathlib import Path

import pytest

from tests.integration import requires_openai

FIXTURES = Path(__file__).parent.parent / "fixtures"

pytestmark = [pytest.mark.integration, requires_openai]


def test_index_and_retrieve_reference_material():
    from src.documents.chunking import chunk_text
    from src.documents.extract import extract_text
    from src.documents.index import default_index

    text = extract_text((FIXTURES / "sample.md").read_bytes(), "sample.md")
    chunks = chunk_text(text, size=300, overlap=50)
    index = default_index()
    assert index.add(chunks) == len(chunks)

    [best] = index.search("How does a cluster elect a leader and replicate its log?", k=1)
    assert "Raft" in chunks[best]
