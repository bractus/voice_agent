"""Unit tests for WAV PCM extraction used in stream_orchestrator."""
import struct
import wave
import tempfile
import os


def build_wav_bytes(sample_rate: int, num_samples: int) -> bytes:
    """Create a minimal in-memory WAV file with silence."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    try:
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b'\x00\x00' * num_samples)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def test_wav_header_is_44_bytes():
    """Standard RIFF PCM WAV header must be exactly 44 bytes."""
    wav_bytes = build_wav_bytes(16000, 100)
    # RIFF magic
    assert wav_bytes[:4] == b'RIFF'
    # WAVE magic at offset 8
    assert wav_bytes[8:12] == b'WAVE'
    # fmt chunk at offset 12
    assert wav_bytes[12:16] == b'fmt '
    # data chunk at offset 36
    assert wav_bytes[36:40] == b'data'


def test_pcm_extraction_length():
    """PCM bytes = total WAV bytes minus the 44-byte header."""
    num_samples = 320
    wav_bytes = build_wav_bytes(16000, num_samples)
    # Each sample is 2 bytes (16-bit)
    expected_pcm_length = num_samples * 2
    pcm_bytes = wav_bytes[44:]
    assert len(pcm_bytes) == expected_pcm_length


def test_pcm_sample_count():
    """Verify sample count from PCM bytes matches expected."""
    num_samples = 640
    wav_bytes = build_wav_bytes(16000, num_samples)
    pcm_bytes = wav_bytes[44:]
    sample_count = len(pcm_bytes) // 2  # 16-bit samples
    assert sample_count == num_samples


def test_silence_pcm_is_all_zeros():
    """Silence WAV produces all-zero PCM bytes."""
    wav_bytes = build_wav_bytes(16000, 50)
    pcm_bytes = wav_bytes[44:]
    assert all(b == 0 for b in pcm_bytes)
