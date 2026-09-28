"""
Per-session document store: the optional resume and the reference material.

Everything lives in memory on the session and is dropped with it (FR-016).
Upload validation follows the order in specs/001-mock-interview-agent/data-model.md.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from src.config import (
    REFERENCE_MAX_BYTES,
    REFERENCE_MAX_CHUNKS,
    REFERENCE_MAX_FILES,
    RESUME_MAX_BYTES,
)
from src.documents.errors import InterviewStartedError, LimitExceededError, UnsupportedFormatError
from src.documents.extract import detect_format

if TYPE_CHECKING:
    from src.documents.index import VectorIndex

__all__ = [
    "RESUME_MAX_BYTES",
    "REFERENCE_MAX_FILES",
    "REFERENCE_MAX_BYTES",
    "REFERENCE_MAX_CHUNKS",
    "Chunk",
    "Document",
    "DocumentSet",
]

DocumentKind = Literal["resume", "reference"]
DocumentFormat = Literal["pdf", "docx", "epub", "txt", "md"]

ALLOWED_FORMATS: dict[DocumentKind, tuple[str, ...]] = {
    "resume": ("pdf", "docx", "txt", "md"),
    "reference": ("pdf", "txt", "epub", "md"),
}

_MB = 1024 * 1024


def _mb(size_bytes: int) -> str:
    return f"{size_bytes / _MB:.1f} MB"


@dataclass
class Document:
    kind: DocumentKind
    filename: str
    format: DocumentFormat
    size_bytes: int
    text: str
    document_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chunk_count: int = 0
    truncated: bool = False


@dataclass
class Chunk:
    chunk_id: int
    document_id: str
    text: str


@dataclass
class DocumentSet:
    resume: Document | None = None
    references: list[Document] = field(default_factory=list)
    reference_bytes_total: int = 0
    index: VectorIndex | None = None
    chunks: list[Chunk] = field(default_factory=list)
    # Serialises reference uploads so two at once can't both pass the limit checks.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def validate_upload(
        self,
        kind: DocumentKind,
        filename: str,
        size_bytes: int,
        uploads_allowed: bool,
    ) -> str:
        """
        Check an upload before its text is extracted: interview stage, then
        format, then size limits. Returns the document format.

        Raises InterviewStartedError, UnsupportedFormatError, or LimitExceededError.
        """
        if not uploads_allowed:
            raise InterviewStartedError("Files can only be uploaded before the interview starts.")

        fmt = detect_format(filename)
        allowed = ALLOWED_FORMATS[kind]
        if fmt not in allowed:
            names = ", ".join(f.upper() if f != "md" else "Markdown" for f in allowed)
            raise UnsupportedFormatError(f"{filename} isn't supported as a {kind}. Use {names}.")

        if kind == "resume":
            self._check_resume_size(size_bytes)
        else:
            self._check_reference_limits(size_bytes)
        return fmt

    def set_resume(self, document: Document) -> None:
        """Store the resume, replacing any previous one."""
        if document.format not in ALLOWED_FORMATS["resume"]:
            raise UnsupportedFormatError(f"{document.filename} isn't supported as a resume.")
        self._check_resume_size(document.size_bytes)
        self.resume = document

    def add_reference(
        self,
        document: Document,
        chunk_texts: list[str],
        index_factory: Callable[[], VectorIndex] | None = None,
    ) -> None:
        """
        Index a reference document's chunks and store it.

        Only the first chunks up to the session cap (REFERENCE_MAX_CHUNKS) are
        indexed; if the cap cuts this document short, `document.truncated` is set.
        Limits are re-checked here, and nothing is stored if embedding fails.
        """
        with self._lock:
            self._check_reference_limits(document.size_bytes)

            remaining = max(0, REFERENCE_MAX_CHUNKS - len(self.chunks))
            kept = chunk_texts[:remaining]
            document.truncated = len(kept) < len(chunk_texts)

            if self.index is None:
                if index_factory is None:
                    from src.documents.index import default_index
                    index_factory = default_index
                self.index = index_factory()
            self.index.add(kept)  # raises before anything is stored if embedding fails

            first_id = len(self.chunks)
            self.chunks.extend(
                Chunk(chunk_id=first_id + i, document_id=document.document_id, text=text)
                for i, text in enumerate(kept)
            )
            document.chunk_count = len(kept)
            self.references.append(document)
            self.reference_bytes_total += document.size_bytes

    def chunk_texts(self, chunk_ids: list[int]) -> list[str]:
        return [self.chunks[i].text for i in chunk_ids]

    def _check_reference_limits(self, size_bytes: int) -> None:
        if len(self.references) >= REFERENCE_MAX_FILES:
            raise LimitExceededError(
                f"You can upload up to {REFERENCE_MAX_FILES} reference files.",
                code="REFERENCE_LIMIT_FILES",
            )
        if self.reference_bytes_total + size_bytes > REFERENCE_MAX_BYTES:
            raise LimitExceededError(
                f"Reference files are limited to {_mb(REFERENCE_MAX_BYTES)} in total. "
                f"{_mb(self.reference_bytes_total)} is already uploaded.",
                code="REFERENCE_LIMIT_SIZE",
            )

    @staticmethod
    def _check_resume_size(size_bytes: int) -> None:
        if size_bytes > RESUME_MAX_BYTES:
            raise LimitExceededError(
                f"Resumes are limited to {_mb(RESUME_MAX_BYTES)}. This file is {_mb(size_bytes)}.",
                code="RESUME_TOO_LARGE",
            )
