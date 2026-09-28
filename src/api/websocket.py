"""
App WebSocket: session lifetime and interview control.

Endpoint: ws://localhost:8000/ws/{session_id}

Connecting creates the session and disconnecting ends it (and any live
interview, without evaluating it). Audio doesn't flow here: it goes over
WebRTC between the browser and GPT-Live. See
specs/002-gpt-live-interview/contracts/websocket-protocol.md.

Client → server text frames: start_session, end_interview, live_disconnected,
mic_muted, and live_event (browser-relay fallback only).
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.session_manager import session_manager
from src.interview.conductor import send_stage
from src.live.control import BrowserRelayControl

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("WebSocket connected: %s", session_id)

    session = session_manager.create(session_id)

    async def send_text(payload: dict) -> None:
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception:
            logger.debug("Frame not sent (WebSocket closed): %s", payload.get("type"))

    session.notify = send_text

    async def invalid_stage(action: str) -> None:
        await send_text({
            "type": "error",
            "code": "INVALID_STAGE",
            "message": f"Can't {action} while the interview is {session.interview.stage.value}.",
        })

    await send_text({"type": "session_created", "session_id": session_id})
    await send_stage(session)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text") is None:
                logger.debug("Ignoring a non-text frame from %s", session_id)
                continue
            try:
                data = json.loads(message["text"])
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from client %s", session_id)
                continue

            msg_type = data.get("type")
            if msg_type == "start_session":
                logger.debug("start_session confirmed for %s", session_id)

            elif msg_type == "end_interview":
                if not session.interview.is_active:
                    await invalid_stage("end the interview")
                    continue
                session.requests.put_nowait(("end", "end_button"))

            elif msg_type == "live_disconnected":
                if session.interview.is_active:
                    logger.info("Browser reports the WebRTC connection lost for %s", session_id)
                    session.requests.put_nowait(("end", "connection_lost"))

            elif msg_type == "mic_muted":
                # The browser mutes GPT-Live directly; the conductor only needs to know that
                # silence is intentional, so it doesn't nudge the interviewer (research.md §7).
                session.requests.put_nowait(("mute", data.get("muted") is True))

            elif msg_type == "live_event":
                if isinstance(session.live, BrowserRelayControl) and isinstance(data.get("event"), dict):
                    session.live.feed(data["event"])

    except WebSocketDisconnect:
        pass
    finally:
        logger.info("WebSocket disconnected: %s", session_id)
        await session.shutdown()
        session_manager.remove(session_id)
