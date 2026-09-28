"""
GPT-Live events: builders for the commands the backend sends, and typed
parsing of the server events the conductor reacts to.

Event names and fields follow the GPT-Live event reference
(specs/002-gpt-live-interview/research.md §1–§7). Parsing never raises: unknown
or malformed events become `Other`, so a new server event can't break a
running interview.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Union


def _event_id() -> str:
    return uuid.uuid4().hex


# ── Commands ──────────────────────────────────────────────────────────────────

def instructions_append(text: str) -> dict:
    assert text, "instructions must not be empty"
    return {"type": "session.instructions.append", "event_id": _event_id(), "delegation_id": None, "content": text}


def commentary_append(delegation_id: str, text: str) -> dict:
    assert text, "commentary must not be empty"
    return {"type": "session.commentary.append", "event_id": _event_id(), "delegation_id": delegation_id, "content": text}


def input_audio_mute() -> dict:
    return {"type": "session.input_audio.mute", "event_id": _event_id()}


def input_audio_unmute() -> dict:
    return {"type": "session.input_audio.unmute", "event_id": _event_id()}


def session_close() -> dict:
    return {"type": "session.close", "event_id": _event_id()}


# ── Server events ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionStarted:
    live_session_id: str


@dataclass(frozen=True)
class TranscriptDelta:
    speaker: Literal["user", "interviewer"]
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class DelegationCreated:
    delegation_id: str
    target: str
    offset_ms: int | None = None   # where on the session timeline the delegation happened


@dataclass(frozen=True)
class CommentaryAppended:
    client_event_id: str | None
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class SessionClosed:
    reason: str


@dataclass(frozen=True)
class LiveError:
    code: str
    message: str
    client_event_id: str | None


@dataclass(frozen=True)
class Other:
    type: str


LiveEvent = Union[SessionStarted, TranscriptDelta, DelegationCreated, CommentaryAppended, SessionClosed, LiveError, Other]


def parse_event(raw: dict) -> LiveEvent:
    """Turn a raw server event (a dict) into a typed event. Never raises."""
    kind = raw.get("type", "") if isinstance(raw, dict) else ""
    try:
        if kind == "session.started":
            return SessionStarted(live_session_id=raw.get("session", {}).get("id", ""))
        if kind in ("session.input_transcript.delta", "session.output_transcript.delta"):
            return TranscriptDelta(
                speaker="user" if kind == "session.input_transcript.delta" else "interviewer",
                text=raw.get("delta", ""),
                start_ms=int(raw.get("start_ms", 0)),
                end_ms=int(raw.get("end_ms", 0)),
            )
        if kind == "session.delegation.created":
            delegation = raw["delegation"]
            offset = raw.get("offset_ms")
            return DelegationCreated(
                delegation_id=delegation["id"],
                target=delegation.get("target", "client"),
                offset_ms=int(offset) if offset is not None else None,
            )
        if kind == "session.commentary.appended":
            return CommentaryAppended(
                client_event_id=raw.get("client_event_id"),
                start_ms=int(raw.get("start_ms", 0)),
                end_ms=int(raw.get("end_ms", 0)),
            )
        if kind == "session.closed":
            return SessionClosed(reason=raw.get("reason", "connection_lost"))
        if kind == "error":
            error = raw.get("error", {})
            return LiveError(
                code=error.get("code", "unknown"),
                message=error.get("message", ""),
                client_event_id=error.get("client_event_id"),
            )
    except (KeyError, TypeError, ValueError):
        pass
    return Other(type=kind)
