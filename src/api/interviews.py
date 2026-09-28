"""
Interview files: the saved transcript and the evaluation report (FR-022).

GET /api/interviews/{interview_id}              summary for the "Last interview" row
GET /api/interviews/{interview_id}/transcript   transcript.md
GET /api/interviews/{interview_id}/report       report.md (or report.json with ?format=json)

Reads only from `config.INTERVIEWS_DIR`, and doesn't need the app WebSocket
session. Contract: specs/002-gpt-live-interview/contracts/http-api.md.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from src import config
from src.interview.record import load_record

router = APIRouter(prefix="/api/interviews/{interview_id}")

_ID_PATTERN = re.compile(r"^[0-9]{8}-[0-9]{6}-(hr|technical)-[a-z0-9]{6}$")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


def _not_found() -> JSONResponse:
    return _error(404, "INTERVIEW_NOT_FOUND", "That interview couldn't be found.")


def _folder(interview_id: str) -> Path | None:
    """The interview's folder, or None if the id is malformed, escapes the folder, or doesn't exist."""
    if not _ID_PATTERN.match(interview_id):
        return None
    root = config.INTERVIEWS_DIR.resolve()
    folder = (root / interview_id).resolve()
    if folder.parent != root or not folder.is_dir():
        return None
    return folder


@router.get("")
async def interview_summary(interview_id: str):
    if _folder(interview_id) is None:
        return _not_found()
    record = load_record(interview_id)
    if record is None:
        return _not_found()
    return {
        "interview_id": record.interview_id,
        "interview_type": record.interview_type,
        "language": record.language,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "end_reason": record.end_reason,
        "question_count": len(record.questions),
        "report_status": record.report_status,
        "role": record.role,
        "seniority": record.seniority,
    }


@router.get("/transcript")
async def transcript(interview_id: str):
    folder = _folder(interview_id)
    if folder is None or not (folder / "transcript.md").is_file():
        return _not_found()
    return FileResponse(
        folder / "transcript.md",
        media_type="text/markdown; charset=utf-8",
        filename=f"interview-{interview_id}.md",
    )


@router.get("/report")
async def report(interview_id: str, format: str = "md"):
    folder = _folder(interview_id)
    if folder is None:
        return _not_found()
    if format == "json":
        path, media_type = folder / "report.json", "application/json"
    else:
        path, media_type = folder / "report.md", "text/markdown; charset=utf-8"
    if not path.is_file():
        return _error(404, "REPORT_NOT_READY", "The report isn't ready yet.")
    if format == "json":
        return FileResponse(path, media_type=media_type)
    return FileResponse(path, media_type=media_type, filename=f"interview-{interview_id}-report.md")
