"""
Creating a GPT-Live session for the browser's WebRTC offer (research.md §1).

The server creates the session with its own key and hands the SDP answer back
to the browser, so the key never reaches the browser (FR-010).
"""
from __future__ import annotations

import logging

from src import config
from src.openai_client import describe_error, get_async_client

logger = logging.getLogger(__name__)

# In sideband mode the browser's data channel may only mute and unmute; every other
# command comes from the trusted server. The relay fallback needs the browser to
# send the server's commands on its behalf.
_BROWSER_EVENTS_SIDEBAND = ["session.input_audio.mute", "session.input_audio.unmute"]


class LiveUnavailableError(Exception):
    """The GPT-Live session couldn't be created or attached."""


def build_session_config(instructions: str) -> dict:
    allowed = _BROWSER_EVENTS_SIDEBAND if config.LIVE_CONTROL == "sideband" else "all"
    return {
        "model": config.OPENAI_LIVE_MODEL,
        "instructions": instructions,
        "audio": {"output": {"voice": config.OPENAI_LIVE_VOICE}},
        "delegation": {"type": "client"},
        "client": {"data_channel": {"allowed_client_events": allowed}},
    }


async def create_live_session(session_config: dict, sdp: str) -> tuple[str, str]:
    """Create the session for the browser's SDP offer. Returns (answer_sdp, live_session_id)."""
    try:
        created = await get_async_client().live.create(
            session=session_config,
            transport={"type": "webrtc", "sdp": sdp},
        )
    except Exception as exc:
        logger.error("GPT-Live session creation failed: %s", describe_error(exc))
        raise LiveUnavailableError("The interviewer couldn't be started.") from exc
    return created.transport.sdp, created.session.id
