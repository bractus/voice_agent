"""
Text-to-Speech — platform-aware.

macOS (default): uses built-in `say` + `afconvert` (Apple Neural TTS, ~100ms).
Linux (Docker):  uses `espeak-ng` (fast, no GPU required).

Set TTS_BACKEND=espeak to force espeak on macOS if desired.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import tempfile

from src.config import MACOS_TTS_VOICE, TTS_BACKEND

logger = logging.getLogger(__name__)

_USE_ESPEAK = TTS_BACKEND == "espeak" or platform.system() != "Darwin"


def synthesise(text: str) -> str:
    """
    Synthesise text to speech and return the path to a 16-bit PCM WAV file.

    Returns:
        Absolute path to a temporary WAV file containing the audio.

    Raises:
        Exception: propagated on failure so the caller can handle it.
    """
    if _USE_ESPEAK:
        return _synthesise_espeak(text)
    return _synthesise_macos(text)


def _synthesise_macos(text: str) -> str:
    aiff_tmp = tempfile.NamedTemporaryFile(suffix=".aiff", delete=False)
    aiff_tmp.close()
    wav_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_tmp.close()
    try:
        subprocess.run(
            ["say", "-v", MACOS_TTS_VOICE, "-o", aiff_tmp.name, text],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["afconvert", aiff_tmp.name, wav_tmp.name,
             "-d", "LEI16@16000", "-c", "1", "-f", "WAVE"],
            check=True, capture_output=True,
        )
        logger.debug("TTS (macOS) output: %s", wav_tmp.name)
        return wav_tmp.name
    finally:
        try:
            os.unlink(aiff_tmp.name)
        except OSError:
            pass


def _synthesise_espeak(text: str) -> str:
    wav_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_tmp.close()
    subprocess.run(
        [
            "espeak-ng",
            "-v", "en-us+f3",   # female voice variant
            "-s", "150",        # speed (words per minute)
            "-a", "80",         # amplitude
            "--sample-rate=16000",
            "-w", wav_tmp.name,
            text,
        ],
        check=True, capture_output=True,
    )
    logger.debug("TTS (espeak) output: %s", wav_tmp.name)
    return wav_tmp.name
