"""
Speech-to-Text — local Whisper via faster-whisper.

Exposes a single `transcribe(audio_path)` function. The WhisperModel
is lazy-loaded once as a module-level singleton.
"""
from __future__ import annotations

import logging

from src.config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model: %s (device=%s)", WHISPER_MODEL, WHISPER_DEVICE)
        _model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        logger.info("Whisper model loaded")
    return _model


def transcribe(audio_path: str) -> str:
    """
    Transcribe an audio file and return the text.

    Args:
        audio_path: Path to a WAV or MP3 file.

    Returns:
        Transcribed text, or empty string if transcription yields nothing
        or an error occurs.
    """
    try:
        model = _get_model()
        segments, _ = model.transcribe(audio_path, language="en", vad_filter=True)
        text = " ".join(s.text for s in segments).strip()
        logger.debug("STT transcript: %r", text)
        return text
    except Exception as exc:
        logger.error("STT transcription failed: %s", exc)
        return ""
