"""
Document upload errors. Each carries the HTTP status and error code from
specs/001-mock-interview-agent/contracts/documents-api.md, and a message
written for the user (shown as-is on the setup screen).
"""
from __future__ import annotations


class DocumentError(Exception):
    status: int = 400
    code: str = "DOCUMENT_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class InterviewStartedError(DocumentError):
    status = 409
    code = "INTERVIEW_STARTED"


class UnsupportedFormatError(DocumentError):
    status = 415
    code = "UNSUPPORTED_FORMAT"


class LimitExceededError(DocumentError):
    """RESUME_TOO_LARGE, REFERENCE_LIMIT_FILES, or REFERENCE_LIMIT_SIZE."""
    status = 413


class DocumentUnreadableError(DocumentError):
    status = 422
    code = "DOCUMENT_UNREADABLE"


class EmbeddingUnavailableError(DocumentError):
    status = 503
    code = "EMBEDDING_UNAVAILABLE"
