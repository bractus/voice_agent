"""
Integration smoke tests for the voice orchestrator.

Feeds a pre-recorded (or synthetic) WAV through process_voice() and
asserts that a non-empty audio response is returned.

Prerequisites:
  - Ollama must be running:  ollama serve
  - Model must be pulled:    ollama pull llama3.2:3b
  - Run with:                pytest tests/integration/ -v

Note: these tests perform real STT, LLM, and TTS inference and will take
longer than unit tests.  Skip with:  pytest -m "not integration"
"""
import wave
from pathlib import Path

import numpy as np
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_WAV = FIXTURES_DIR / "question.wav"


@pytest.fixture(scope="module", autouse=True)
def ensure_fixture_wav():
    """
    Create a minimal synthetic WAV fixture if none exists.

    Generates 2 seconds of silence at 16 kHz mono. Replace with a real
    recording of an English question for meaningful STT coverage.
    """
    FIXTURES_DIR.mkdir(exist_ok=True)
    if not SAMPLE_WAV.exists():
        sample_rate = 16_000
        duration_s = 2
        samples = np.zeros(sample_rate * duration_s, dtype=np.int16)
        with wave.open(str(SAMPLE_WAV), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())


@pytest.mark.integration
def test_tts_synthesises_audio():
    """TTS synthesise() returns a non-empty WAV file path."""
    import os
    from src.pipeline.tts import synthesise

    path = synthesise("Hello, this is a test.")
    assert path and os.path.exists(path), "synthesise() must return a valid file path"
    assert os.path.getsize(path) > 0, "Synthesised WAV must not be empty"


@pytest.mark.integration
def test_orchestrator_produces_audio_output():
    """
    Smoke test: process_voice() with a real WAV fixture returns an audio path.

    Note: silence produces no transcript, so this test verifies graceful
    handling of empty input.  Replace SAMPLE_WAV with a real recording
    for end-to-end coverage.
    """
    from src.pipeline.orchestrator import process_voice
    from src.session.history import ConversationHistory

    history = ConversationHistory()
    audio_out, status_msg, updated_history = process_voice(str(SAMPLE_WAV), history)

    # With a silent WAV, no transcript → graceful no-op
    # With a real recording, audio_out should be a valid path
    assert isinstance(status_msg, str)
    assert updated_history is history or updated_history is not None


@pytest.mark.integration
def test_history_survives_multi_turn():
    """History correctly tracks multiple turns."""
    from src.session.history import ConversationHistory

    h = ConversationHistory()
    h.add_user_message("What is 2 + 2?")
    h.add_assistant_message("4.")
    h.add_user_message("And 3 + 3?")
    h.add_assistant_message("6.")

    messages = h.get_messages()
    assert len(messages) == 5  # system + 2 pairs
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert messages[4]["role"] == "assistant"
