"""
Voice pipeline orchestrator.

Chains STT → LLM → TTS and manages conversation history.
Called by the Gradio UI for each user interaction.
"""
from __future__ import annotations

import logging
import os

from src.pipeline.stt import transcribe
from src.pipeline.llm import chat
from src.pipeline.tts import synthesise
from src.session.history import ConversationHistory

logger = logging.getLogger(__name__)


def process_voice(
    audio_path: str | None,
    history: ConversationHistory,
) -> tuple[str | None, str, ConversationHistory]:
    """
    Process a voice recording through the full pipeline.

    Args:
        audio_path: Path to the recorded audio file provided by Gradio,
                    or None if no audio was captured.
        history:    Session conversation history (modified in place and returned).

    Returns:
        A 3-tuple of:
          - audio_out:  Path to the synthesised TTS WAV, or None on failure.
          - status_msg: Empty string on success; human-readable error otherwise.
          - history:    Updated ConversationHistory.
    """
    if audio_path is None or not os.path.exists(audio_path):
        return None, "", history

    # ── STT ───────────────────────────────────────────────────────────────────
    transcript = transcribe(audio_path)
    if not transcript:
        logger.info("No speech detected in recording")
        return None, "No speech detected — please try again.", history

    logger.info("User: %s", transcript)
    history.add_user_message(transcript)

    # ── LLM ───────────────────────────────────────────────────────────────────
    try:
        reply = chat(history.get_messages())
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        # Undo the user message so history stays consistent
        history._messages.pop()
        return None, "Assistant unavailable — is Ollama running?", history

    logger.info("Assistant: %s", reply)
    history.add_assistant_message(reply)

    # ── TTS ───────────────────────────────────────────────────────────────────
    try:
        audio_out = synthesise(reply)
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        return None, "Could not synthesise audio response.", history

    return audio_out, "", history
