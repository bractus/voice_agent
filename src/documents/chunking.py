"""
Split reference text into overlapping chunks for embedding (research.md §5).

Chunks are about CHUNK_SIZE characters, and each starts about CHUNK_OVERLAP
characters before the previous one ended, so an idea that straddles a
boundary still appears whole in one chunk. Cuts prefer a paragraph break,
then a sentence end, then a space.
"""
from __future__ import annotations

import re

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

_SENTENCE_END = re.compile(r"[.!?…](?=\s)")


def _best_cut(window: str, min_pos: int) -> int:
    """Return where to end a chunk within `window`, preferring natural breaks after `min_pos`."""
    paragraph = window.rfind("\n\n")
    if paragraph >= min_pos:
        return paragraph
    sentence_ends = [m.end() for m in _SENTENCE_END.finditer(window) if m.end() >= min_pos]
    if sentence_ends:
        return sentence_ends[-1]
    space = window.rfind(" ")
    if space >= min_pos:
        return space
    return len(window)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split `text` into chunks of at most `size` characters, overlapping by about `overlap`."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            end = start + _best_cut(text[start:end], min_pos=size // 2)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break

        # Step back by the overlap, then forward to the start of a word.
        next_start = end - overlap
        space = text.find(" ", next_start, end)
        if space != -1:
            next_start = space + 1
        start = max(next_start, start + 1)
    return chunks
