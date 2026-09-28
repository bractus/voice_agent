"""
Documents HTTP API — upload a resume or reference material before the interview.

POST /api/sessions/{session_id}/documents   upload one file (multipart: kind + file)
GET  /api/sessions/{session_id}/documents   list what has been accepted so far

Contract: specs/001-mock-interview-agent/contracts/documents-api.md
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from src.api.session_manager import ConversationSession, session_manager
from src.documents.chunking import chunk_text
from src.documents.errors import DocumentError
from src.documents.extract import extract_text
from src.interview.resume_reader import suggest_from_resume
from src.documents.store import (
    REFERENCE_MAX_BYTES,
    REFERENCE_MAX_FILES,
    RESUME_MAX_BYTES,
    Document,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions/{session_id}/documents")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


def _session_not_found() -> JSONResponse:
    return _error(404, "SESSION_NOT_FOUND", "Your session has expired. Please reload the page.")


def _document_json(document: Document) -> dict:
    return {
        "document_id": document.document_id,
        "kind": document.kind,
        "filename": document.filename,
        "format": document.format,
        "size_bytes": document.size_bytes,
        "chunk_count": document.chunk_count,
        "truncated": document.truncated,
    }


def _process_upload(session: ConversationSession, kind: str, filename: str, data: bytes) -> Document:
    """Validate, extract, and store one upload (indexing reference files). Runs in a worker thread."""
    documents = session.documents
    fmt = documents.validate_upload(kind, filename, len(data), session.interview.uploads_allowed)
    text = extract_text(data, filename)
    document = Document(kind=kind, filename=filename, format=fmt, size_bytes=len(data), text=text)
    if kind == "resume":
        documents.set_resume(document)
    else:
        documents.add_reference(document, chunk_text(text))
    return document


@router.post("", status_code=201)
async def upload_document(
    session_id: str,
    kind: Literal["resume", "reference"] = Form(...),
    file: UploadFile = File(...),
):
    session = session_manager.get(session_id)
    if session is None:
        return _session_not_found()

    filename = file.filename or "upload"
    data = await file.read()

    try:
        document = await asyncio.to_thread(_process_upload, session, kind, filename, data)
    except DocumentError as exc:
        logger.info("Upload rejected (%s) for session %s: %s", exc.code, session_id, filename)
        return _error(exc.status, exc.code, exc.message)

    logger.info(
        "Accepted %s %s (%d bytes, %d chunks%s) for session %s",
        kind, filename, len(data), document.chunk_count,
        ", truncated" if document.truncated else "", session_id,
    )
    documents = session.documents
    body = {
        **_document_json(document),
        "reference_bytes_total": documents.reference_bytes_total,
        "reference_count": len(documents.references),
    }
    if kind == "resume":
        # Role and seniority suggested from the resume (003 FR-004); None never blocks the upload.
        body["suggestion"] = await suggest_from_resume(document.text)
    return JSONResponse(body, status_code=201)


@router.get("")
async def list_documents(session_id: str):
    session = session_manager.get(session_id)
    if session is None:
        return _session_not_found()

    documents = session.documents
    resume = documents.resume
    return {
        "resume": (
            {
                "document_id": resume.document_id,
                "filename": resume.filename,
                "format": resume.format,
                "size_bytes": resume.size_bytes,
            }
            if resume
            else None
        ),
        "references": [
            {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "format": doc.format,
                "size_bytes": doc.size_bytes,
                "chunk_count": doc.chunk_count,
                "truncated": doc.truncated,
            }
            for doc in documents.references
        ],
        "reference_bytes_total": documents.reference_bytes_total,
        "limits": {
            "reference_max_files": REFERENCE_MAX_FILES,
            "reference_max_bytes": REFERENCE_MAX_BYTES,
            "resume_max_bytes": RESUME_MAX_BYTES,
        },
    }
