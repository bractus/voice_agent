"""
WebSocket endpoint for the real-time voice protocol.

Endpoint: ws://localhost:8000/ws/{session_id}

Handles:
  - Binary frames: PCM audio chunks from the user
  - Text frames (JSON): start_session, end_utterance, barge_in
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.session_manager import session_manager
from src.pipeline.stream_orchestrator import stream_voice

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("WebSocket connected: %s", session_id)

    session = session_manager.create(session_id)
    audio_buffer = bytearray()

    async def send_text(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload))

    async def send_bytes(data: bytes) -> None:
        await websocket.send_bytes(data)

    await send_text({"type": "session_created", "session_id": session_id})
    await send_text({"type": "state_change", "state": "idle"})

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                # Binary frame: PCM audio from user
                audio_buffer.extend(message["bytes"])

            elif "text" in message and message["text"] is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from client: %r", message["text"])
                    continue

                msg_type = data.get("type")

                if msg_type == "start_session":
                    logger.debug("start_session confirmed for %s", session_id)

                elif msg_type == "end_utterance":
                    buffered = bytes(audio_buffer)
                    audio_buffer.clear()
                    session.state = "processing"
                    await send_text({"type": "state_change", "state": "processing"})
                    session.state = "agent_speaking"
                    await send_text({"type": "state_change", "state": "agent_speaking"})

                    await stream_voice(buffered, session, send_text, send_bytes)

                    session.state = "idle"
                    await send_text({"type": "state_change", "state": "idle"})

                elif msg_type == "barge_in":
                    logger.info("Barge-in received for session %s", session_id)
                    session.barge_in_event.set()
                    session.state = "interrupted"
                    await send_text({"type": "state_change", "state": "interrupted"})
                    session.state = "listening"
                    await send_text({"type": "state_change", "state": "listening"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    finally:
        session_manager.remove(session_id)
