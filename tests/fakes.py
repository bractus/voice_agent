"""Test doubles shared by the contract tests."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from src.live.events import (
    LiveEvent,
    SessionClosed,
    commentary_append,
    instructions_append,
    parse_event,
    session_close,
)


class FakeLiveControl:
    """
    A scripted GPT-Live control plane (implements src.live.control.LiveControl).

    `push(raw_event)` feeds a server event (dict, as GPT-Live would send it) to the
    conductor. Every command the conductor sends is recorded in `sent`. After
    close() the stream ends with SessionClosed("close_requested"); `drop()` ends
    it with SessionClosed("connection_lost") instead.
    """

    def __init__(self, live_session_id: str = "sess_fake", events: list[dict] | None = None) -> None:
        self.live_session_id = live_session_id
        self.sent: list[dict] = []
        self.closed = False
        self._queue: asyncio.Queue = asyncio.Queue()
        for raw in events or []:
            self._queue.put_nowait(raw)

    # ── Test controls ─────────────────────────────────────────────────────────

    def push(self, raw_event: dict) -> None:
        self._queue.put_nowait(raw_event)

    def drop(self) -> None:
        self._queue.put_nowait(SessionClosed(reason="connection_lost"))

    def sent_of_type(self, kind: str) -> list[dict]:
        return [c for c in self.sent if c["type"] == kind]

    # ── LiveControl ───────────────────────────────────────────────────────────

    async def events(self) -> AsyncIterator[LiveEvent]:
        while True:
            item = await self._queue.get()
            event = item if isinstance(item, SessionClosed) else parse_event(item)
            yield event
            if isinstance(event, SessionClosed):
                return

    async def send(self, command: dict) -> None:
        self.sent.append(command)

    async def append_instructions(self, text: str) -> dict:
        command = instructions_append(text)
        await self.send(command)
        return command

    async def append_commentary(self, delegation_id: str, text: str) -> dict:
        command = commentary_append(delegation_id, text)
        await self.send(command)
        return command

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.send(session_close())
        self._queue.put_nowait(SessionClosed(reason="close_requested"))


# ── Raw GPT-Live server events ────────────────────────────────────────────────

def started(session_id: str = "sess_fake") -> dict:
    return {"type": "session.started", "session": {"id": session_id}}


def delegation(delegation_id: str, offset_ms: int = 0) -> dict:
    return {"type": "session.delegation.created", "offset_ms": offset_ms,
            "delegation": {"id": delegation_id, "type": "delegation", "target": "client"}}


def appended(client_event_id: str, start_ms: int) -> dict:
    return {"type": "session.commentary.appended", "client_event_id": client_event_id,
            "start_ms": start_ms, "end_ms": start_ms}


def user_says(text: str, start_ms: int, end_ms: int | None = None) -> dict:
    return {"type": "session.input_transcript.delta", "delta": text,
            "start_ms": start_ms, "end_ms": end_ms if end_ms is not None else start_ms + 500}


def interviewer_says(text: str, start_ms: int, end_ms: int | None = None) -> dict:
    return {"type": "session.output_transcript.delta", "delta": text,
            "start_ms": start_ms, "end_ms": end_ms if end_ms is not None else start_ms + 500}


def error(code: str, client_event_id: str | None = None) -> dict:
    return {"type": "error", "error": {"type": "invalid_request_error", "code": code,
                                        "message": code, "client_event_id": client_event_id}}
