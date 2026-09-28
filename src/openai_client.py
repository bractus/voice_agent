"""
OpenAI clients and the API-key check.

The clients are created lazily, like the other model singletons in this
project. The key comes from src/.env via src.config and never leaves the
server (FR-010): nothing here logs headers, and OpenAI errors are logged by
type/code only.
"""
from __future__ import annotations

import logging
import time
from typing import Literal

import httpx
import openai

from src import config

logger = logging.getLogger(__name__)

OpenAIStatus = Literal["ok", "missing_key", "invalid_key", "model_unavailable", "unavailable"]

# Messages shown as-is on the setup screen (contracts/http-api.md).
STATUS_MESSAGES: dict[str, str | None] = {
    "ok": None,
    "missing_key": (
        "The interviewer is unavailable: no OpenAI API key is configured. "
        "Add OPENAI_API_KEY to src/.env and restart the app."
    ),
    "invalid_key": (
        "The interviewer is unavailable: the OpenAI API key was rejected. "
        "Check OPENAI_API_KEY in src/.env."
    ),
    "model_unavailable": (
        "The interviewer is unavailable: this OpenAI account can't use the gpt-live-1 model. "
        "Check the account's model access."
    ),
    "unavailable": (
        "The interviewer is unavailable: OpenAI can't be reached right now. Try again in a moment."
    ),
}

_STATUS_CACHE_SECONDS = 60

_async_client: openai.AsyncOpenAI | None = None
_sync_client: openai.OpenAI | None = None
_status_cache: tuple[OpenAIStatus, float] | None = None


def get_async_client() -> openai.AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _async_client


def get_sync_client() -> openai.OpenAI:
    global _sync_client
    if _sync_client is None:
        _sync_client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    return _sync_client


def describe_error(exc: BaseException) -> str:
    """A log-safe description of an OpenAI error: its class and code, never its body or headers."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return f"{type(exc).__name__}({code})" if code else type(exc).__name__


async def check_openai() -> OpenAIStatus:
    """Whether the configured key can use the live model. Cached for 60 s."""
    global _status_cache
    if _status_cache is not None and time.monotonic() - _status_cache[1] < _STATUS_CACHE_SECONDS:
        return _status_cache[0]

    status: OpenAIStatus
    if not config.OPENAI_API_KEY:
        status = "missing_key"
    else:
        try:
            await get_async_client().models.retrieve(config.OPENAI_LIVE_MODEL)
            status = "ok"
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            status = "invalid_key"
        except openai.NotFoundError:
            status = "model_unavailable"
        except (openai.APIError, httpx.HTTPError) as exc:
            logger.warning("OpenAI key check failed: %s", describe_error(exc))
            status = "unavailable"

    _status_cache = (status, time.monotonic())
    return status
