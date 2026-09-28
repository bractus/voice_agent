"""
The control plane of a GPT-Live session (research.md §1).

The conductor only talks to the `LiveControl` interface. Two transports
implement it:
  - SidebandControl: a trusted server WebSocket attached to the session (default).
  - BrowserRelayControl: the browser forwards its data-channel events over the
    app WebSocket and sends the server's commands for it (fallback).
Tests use tests/fakes.py:FakeLiveControl.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol

from src import config
from src.live.events import (
    LiveEvent,
    SessionClosed,
    commentary_append,
    instructions_append,
    parse_event,
    session_close,
)
from src.live.session import LiveUnavailableError
from src.openai_client import describe_error, get_async_client

logger = logging.getLogger(__name__)

SendText = Callable[[dict], Awaitable[None]]

_CLOSE_DRAIN_SECONDS = 10


class LiveControl(Protocol):
    live_session_id: str

    def events(self) -> AsyncIterator[LiveEvent]: ...

    async def send(self, command: dict) -> None: ...

    async def append_instructions(self, text: str) -> dict: ...

    async def append_commentary(self, delegation_id: str, text: str) -> dict: ...

    async def close(self) -> None: ...


class _ControlBase:
    """Shared command helpers. Subclasses provide send(), events() and _detach()."""

    live_session_id: str
    closed: bool = False

    async def send(self, command: dict) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def append_instructions(self, text: str) -> dict:
        command = instructions_append(text)
        await self.send(command)
        return command

    async def append_commentary(self, delegation_id: str, text: str) -> dict:
        command = commentary_append(delegation_id, text)
        await self.send(command)
        return command

    async def close(self) -> None:
        """Ask GPT-Live to end the session; the conductor sees SessionClosed on its event stream."""
        if self.closed:
            return
        self.closed = True
        try:
            await self.send(session_close())
        except Exception as exc:
            logger.warning("session.close failed: %s", describe_error(exc))
        asyncio.get_running_loop().call_later(_CLOSE_DRAIN_SECONDS, self._detach)

    def _detach(self) -> None:  # pragma: no cover - overridden
        pass


class SidebandControl(_ControlBase):
    """A server-side WebSocket attached to the running WebRTC session."""

    def __init__(self, live_session_id: str, connection, manager) -> None:
        self.live_session_id = live_session_id
        self._connection = connection
        self._manager = manager

    @classmethod
    async def attach(cls, live_session_id: str) -> SidebandControl:
        manager = get_async_client().live.sideband.connect(
            session_id=live_session_id,
            # Notice a dead network within ~5 s (SC-007) instead of the 20 s + 20 s default.
            websocket_connection_options={"ping_interval": 2, "ping_timeout": 3},
            max_retries=0,
        )
        try:
            connection = await manager.__aenter__()
        except Exception as exc:
            logger.error("Sideband attach failed: %s", describe_error(exc))
            raise LiveUnavailableError("The interviewer couldn't be started.") from exc
        return cls(live_session_id, connection, manager)

    async def events(self) -> AsyncIterator[LiveEvent]:
        try:
            async for event in self._connection:
                yield parse_event(event.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("Sideband connection dropped: %s", describe_error(exc))
        # However the stream ends, the conductor learns the session is gone.
        yield SessionClosed(reason="close_requested" if self.closed else "connection_lost")

    async def send(self, command: dict) -> None:
        await self._connection.send(command)

    def _detach(self) -> None:
        asyncio.ensure_future(self._manager.__aexit__(None, None, None))


class BrowserRelayControl(_ControlBase):
    """Fallback: the browser relays data-channel events and commands over the app WebSocket."""

    def __init__(self, live_session_id: str, send_text: SendText) -> None:
        self.live_session_id = live_session_id
        self._send_text = send_text
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def feed(self, raw_event: dict) -> None:
        self._queue.put_nowait(raw_event)

    async def events(self) -> AsyncIterator[LiveEvent]:
        while True:
            raw = await self._queue.get()
            if raw is None:
                yield SessionClosed(reason="close_requested" if self.closed else "connection_lost")
                return
            yield parse_event(raw)

    async def send(self, command: dict) -> None:
        await self._send_text({"type": "live_command", "event": command})

    def _detach(self) -> None:
        self._queue.put_nowait(None)


async def attach_control(live_session_id: str, send_text: SendText) -> LiveControl:
    """The control plane for a new session, chosen by LIVE_CONTROL."""
    if config.LIVE_CONTROL == "browser_relay":
        return BrowserRelayControl(live_session_id, send_text)
    return await SidebandControl.attach(live_session_id)
