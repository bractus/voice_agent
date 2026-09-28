"""
In-memory session registry: one session per app WebSocket connection.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.documents.store import DocumentSet
from src.interview.state import Interview, InterviewStage

if TYPE_CHECKING:
    from src.live.control import LiveControl

logger = logging.getLogger(__name__)

SendText = Callable[[dict], Awaitable[None]]


async def _no_notify(payload: dict) -> None:
    pass


@dataclass
class ConversationSession:
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    interview: Interview = field(default_factory=Interview)
    documents: DocumentSet = field(default_factory=DocumentSet)
    # The GPT-Live control plane, from POST /api/sessions/{id}/live until the interview ends.
    live: LiveControl | None = None
    conductor_task: asyncio.Task | None = None
    # The running interview's conductor state (src.interview.conductor.InterviewRun).
    run: object | None = None
    # Sends a JSON frame to this session's browser (set by the WebSocket endpoint).
    notify: SendText = _no_notify
    # Control requests for the conductor's loop: ("end", reason) from the app WebSocket.
    requests: asyncio.Queue = field(default_factory=asyncio.Queue)

    async def shutdown(self) -> None:
        """The app WebSocket is gone: end any live interview without evaluating it, and free the session."""
        from src.interview import conductor

        if self.interview.is_active:
            await conductor.on_page_closed(self)
        if self.conductor_task is not None and not self.conductor_task.done():
            self.conductor_task.cancel()
        if self.live is not None and not getattr(self.live, "closed", False):
            try:
                await self.live.close()
            except Exception as exc:
                logger.warning("Closing the live session failed: %s", type(exc).__name__)
        if self.interview.stage not in (InterviewStage.SETUP, InterviewStage.CONCLUDED):
            logger.info("Session %s shut down in stage %s", self.session_id, self.interview.stage.value)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    def create(self, session_id: str) -> ConversationSession:
        session = ConversationSession(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("Session created: %s", session_id)
        return session

    def get(self, session_id: str) -> ConversationSession | None:
        return self._sessions.get(session_id)

    def all(self) -> list[ConversationSession]:
        return list(self._sessions.values())

    def remove(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("Session removed: %s", session_id)


session_manager = SessionManager()
