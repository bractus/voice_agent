"""
Streaming voice orchestrator.

Chains STT → streaming LLM → sentence splitter → TTS for each sentence,
sending audio chunks over a WebSocket connection as soon as each sentence
is ready. Supports barge-in cancellation via an asyncio.Event.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import wave
from collections.abc import Callable, Awaitable

from src.pipeline.stt import transcribe
from src.pipeline.llm import stream_chat
from src.pipeline.tts import synthesise
from src.pipeline.sentence_splitter import split_sentences
from src.api.session_manager import ConversationSession

logger = logging.getLogger(__name__)

SendText = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

# Standard WAV header size (RIFF PCM)
_WAV_HEADER_SIZE = 44


def _read_pcm_from_wav(wav_path: str) -> bytes:
    """Read raw PCM bytes from a WAV file, stripping the RIFF header."""
    with wave.open(wav_path, "rb") as wf:
        return wf.readframes(wf.getnframes())


async def stream_voice(
    audio_bytes: bytes,
    session: ConversationSession,
    send_text: SendText,
    send_bytes: SendBytes,
) -> None:
    """
    Process a user utterance and stream TTS audio sentence-by-sentence.

    Args:
        audio_bytes: Raw WAV bytes of the user's recorded utterance.
        session:     Active ConversationSession (history + barge_in_event).
        send_text:   Coroutine that sends a JSON dict as a WebSocket text frame.
        send_bytes:  Coroutine that sends raw bytes as a WebSocket binary frame.
    """
    # Write audio bytes to a temp file for STT
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        # ── STT ───────────────────────────────────────────────────────────────
        transcript = await asyncio.to_thread(transcribe, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not transcript:
        logger.info("No speech detected")
        await send_text({"type": "error", "code": "STT_FAILED", "message": "No speech detected."})
        return

    logger.info("User: %s", transcript)
    session.history.add_user_message(transcript)
    await send_text({"type": "transcript", "text": transcript})

    # ── Streaming LLM + sentence-by-sentence TTS ──────────────────────────────
    # LLM tokens stream into the sentence splitter in a background thread.
    # Each completed sentence is pushed to an async queue so TTS can start
    # on sentence 1 while the LLM is still generating sentence 2.
    session.barge_in_event.clear()
    sentence_index = 0
    full_reply_parts: list[str] = []

    sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _produce_sentences() -> None:
        """Run in a thread: stream LLM tokens → split → push sentences."""
        try:
            token_gen = stream_chat(session.history.get_messages())
            for sentence in split_sentences(token_gen):
                loop.call_soon_threadsafe(sentence_queue.put_nowait, sentence)
        except Exception as exc:
            logger.error("LLM streaming failed: %s", exc)
            loop.call_soon_threadsafe(sentence_queue.put_nowait, None)
            return
        loop.call_soon_threadsafe(sentence_queue.put_nowait, None)  # sentinel

    producer = asyncio.get_event_loop().run_in_executor(None, _produce_sentences)

    async def _sentences():
        while True:
            item = await sentence_queue.get()
            if item is None:
                break
            yield item

    try:
        async for sentence in _sentences():
            if session.barge_in_event.is_set():
                logger.info("Barge-in detected — stopping TTS at sentence %d", sentence_index)
                break

            logger.debug("Synthesising sentence %d: %r", sentence_index, sentence)
            full_reply_parts.append(sentence)

            try:
                wav_path = await asyncio.to_thread(synthesise, sentence)
            except Exception as exc:
                logger.error("TTS failed for sentence %d: %s", sentence_index, exc)
                await send_text({
                    "type": "error",
                    "code": "TTS_FAILED",
                    "message": "Could not synthesise audio response.",
                })
                break

            pcm_bytes = await asyncio.to_thread(_read_pcm_from_wav, wav_path)
            try:
                os.unlink(wav_path)
            except OSError:
                pass

            await send_text({
                "type": "agent_text_chunk",
                "text": sentence,
                "sentence_index": sentence_index,
            })
            await send_bytes(pcm_bytes)
            sentence_index += 1
    finally:
        await producer  # ensure the producer thread is done

    await send_text({"type": "agent_done", "total_sentences": sentence_index})

    # Only append assistant message if at least one sentence was delivered
    if full_reply_parts:
        session.history.add_assistant_message(" ".join(full_reply_parts))
