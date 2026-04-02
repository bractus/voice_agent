"""
Sentence boundary splitter for streaming LLM token output.

Buffers incoming tokens and yields complete sentences so each sentence
can be synthesised to audio independently, enabling streaming TTS.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

# Sentence-ending punctuation followed by whitespace or end-of-string
_SENTENCE_END = re.compile(r'[.!?…]+(?:\s+|$)')
_MIN_LENGTH = 3


def split_sentences(token_stream: Iterator[str]) -> Iterator[str]:
    """
    Consume a stream of text tokens and yield complete sentences.

    A sentence boundary is detected when the buffer contains terminal
    punctuation (.  !  ?  …) followed by whitespace or end of stream.
    Flushes any remaining buffer when the stream is exhausted.

    Args:
        token_stream: Iterator of string tokens (e.g. LLM streaming deltas).

    Yields:
        Complete sentences as strings (stripped).
    """
    buf = ""
    for token in token_stream:
        buf += token
        # Look for a sentence boundary inside the buffer
        while True:
            m = _SENTENCE_END.search(buf)
            if m is None:
                break
            sentence = buf[:m.end()].strip()
            buf = buf[m.end():]
            if len(sentence) >= _MIN_LENGTH:
                yield sentence

    # Flush remaining buffer
    remainder = buf.strip()
    if len(remainder) >= _MIN_LENGTH:
        yield remainder
