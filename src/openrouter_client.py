"""
The OpenRouter client, used by the feedback grader (Jev).

Like src/openai_client.py: the client is created lazily, and the key comes from
src/.env via src.config. It never leaves the server (specs/004 FR-015): it sits
only in the Authorization header of this client, and errors are logged by class
and status, never by body or headers.
"""
from __future__ import annotations

import httpx

from src import config

OPENROUTER_BASE_URL = "https://openrouter.ai"

_client: httpx.AsyncClient | None = None


def get_openrouter_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "X-OpenRouter-Title": "Dev Fairy",
            },
        )
    return _client


def reset_client() -> None:
    """Forget the client, so the next call builds one with the current key (tests, a new event loop)."""
    global _client
    _client = None


def describe_http_error(exc: BaseException) -> str:
    """A log-safe description of an HTTP error: its class and status, never its body or headers."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return f"{type(exc).__name__}({status})" if status else type(exc).__name__
