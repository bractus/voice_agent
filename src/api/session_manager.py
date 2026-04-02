"""
In-memory session registry for WebSocket voice sessions.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.session.history import ConversationHistory

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    session_id: str
    history: ConversationHistory = field(default_factory=ConversationHistory)
    state: str = "idle"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    barge_in_event: asyncio.Event = field(default_factory=asyncio.Event)


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

    def remove(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("Session removed: %s", session_id)


session_manager = SessionManager()
