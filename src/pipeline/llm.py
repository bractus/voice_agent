"""
Language Model — Ollama via its OpenAI-compatible endpoint.

Exposes a single `chat(messages)` function. The OpenAI client is
lazy-created once as a module-level singleton.
"""
from __future__ import annotations

import logging

from src.config import OLLAMA_API_BASE, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(base_url=OLLAMA_API_BASE, api_key="ollama")
        logger.info("OpenAI client initialised (base_url=%s, model=%s)", OLLAMA_API_BASE, OLLAMA_MODEL)
    return _client


from collections.abc import Iterator


def stream_chat(messages: list[dict]) -> Iterator[str]:
    """
    Stream a chat completion from Ollama token by token.

    Yields:
        Text delta strings as they arrive from the model.

    Raises:
        Exception: propagated on network or API error.
    """
    client = _get_client()
    stream = client.chat.completions.create(
        model=OLLAMA_MODEL, messages=messages, stream=True
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


def chat(messages: list[dict]) -> str:
    """
    Send a chat completion request to Ollama and return the reply text.

    Args:
        messages: OpenAI-format message list (includes system prompt).

    Returns:
        Assistant reply string.

    Raises:
        Exception: propagated on network or API error so the caller can
                   decide whether to show an error to the user.
    """
    client = _get_client()
    response = client.chat.completions.create(model=OLLAMA_MODEL, messages=messages)
    reply = response.choices[0].message.content
    logger.debug("LLM reply: %r", reply)
    return reply
