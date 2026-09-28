"""Integration tests call the real OpenAI API."""
import pytest


@pytest.fixture(autouse=True)
def _fresh_openai_client(monkeypatch):
    """Each async test runs on its own event loop; a cached AsyncOpenAI client would still be
    bound to a closed one (RuntimeError: Event loop is closed). The app itself runs one loop."""
    monkeypatch.setattr("src.openai_client._async_client", None)
    monkeypatch.setattr("src.openrouter_client._client", None)
