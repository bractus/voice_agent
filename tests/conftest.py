"""Shared pytest fixtures."""
import zlib

import pytest

EMBED_DIM = 64


def fake_embed(text: str) -> list[float]:
    """Bag-of-words hashed into a fixed-size vector: shared words → similar vectors."""
    vec = [0.0] * EMBED_DIM
    for word in text.lower().split():
        vec[zlib.crc32(word.strip(".,?:;").encode()) % EMBED_DIM] += 1.0
    vec[0] += 0.01  # never an all-zero vector
    return vec


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Replace the OpenAI embedding calls with a deterministic local embedder."""
    monkeypatch.setattr(
        "src.documents.embeddings.embed_documents",
        lambda texts: [fake_embed(t) for t in texts],
    )
    monkeypatch.setattr("src.documents.embeddings.embed_query", fake_embed)


@pytest.fixture
def tmp_interviews_dir(monkeypatch, tmp_path):
    """Point interview records and reports at a temp folder (modules read config at call time)."""
    path = tmp_path / "interviews"
    monkeypatch.setattr("src.config.INTERVIEWS_DIR", path)
    return path


@pytest.fixture
def openai_ok(monkeypatch):
    """Report the OpenAI key as valid without calling the API."""
    async def ok() -> str:
        return "ok"
    monkeypatch.setattr("src.openai_client.check_openai", ok)


@pytest.fixture
def fake_resume_reader(monkeypatch):
    """Replace the resume reader (a model call) with a scripted result; default: no suggestion."""
    state = {"value": None, "calls": 0}

    async def fake(text):
        state["calls"] += 1
        if isinstance(state["value"], Exception):
            raise state["value"]
        return state["value"]

    monkeypatch.setattr("src.api.documents.suggest_from_resume", fake, raising=False)
    return state
