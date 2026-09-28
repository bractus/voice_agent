"""
POST /api/sessions/{session_id}/live — start the interview.

Fixes the interview type and language, creates the GPT-Live session for the
browser's WebRTC offer with the server's key, attaches the control plane and
starts the conductor. Contract: specs/002-gpt-live-interview/contracts/http-api.md.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src import openai_client
from src.api.session_manager import session_manager
from src.config import SUPPORTED_LANGUAGES
from src.interview import conductor
from src.interview.prompts import build_interviewer_instructions
from src.interview.state import INTERVIEW_TYPES, ROLE_MAX_CHARS, SENIORITIES, normalise_role
from src.live import control as live_control
from src.live import session as live_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions/{session_id}/live")

_START_FAILED = "The interviewer couldn't be started. Try again in a moment."


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


@router.post("", status_code=201)
async def start_live(session_id: str, request: Request):
    session = session_manager.get(session_id)
    if session is None:
        return _error(404, "SESSION_NOT_FOUND", "Your session has expired. Please reload the page.")
    if not session.interview.uploads_allowed:
        return _error(409, "INTERVIEW_STARTED", "The interview has already started.")

    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    interview_type = body.get("interview_type")
    language = body.get("language") or "en"
    role = normalise_role(body.get("role"))
    seniority = body.get("seniority") or "mid"
    sdp = body.get("sdp")

    if interview_type not in INTERVIEW_TYPES:
        return _error(422, "INVALID_INTERVIEW_TYPE", "Choose an HR or a technical interview.")
    if language not in SUPPORTED_LANGUAGES:
        return _error(422, "INVALID_LANGUAGE", "Choose English or Português (Brasil).")
    if role is not None and len(role) > ROLE_MAX_CHARS:
        return _error(422, "INVALID_ROLE", f"The role can have at most {ROLE_MAX_CHARS} characters.")
    if seniority not in SENIORITIES:
        return _error(422, "INVALID_SENIORITY", "Choose junior, mid-level or senior.")
    if not isinstance(sdp, str) or not sdp.strip():
        return _error(422, "INVALID_SDP", "The browser didn't send a connection offer. Please reload the page.")

    status = await openai_client.check_openai()
    if status != "ok":
        code = "OPENAI_UNAVAILABLE" if status == "unavailable" else "OPENAI_NOT_CONFIGURED"
        return _error(503, code, openai_client.STATUS_MESSAGES[status])

    documents = session.documents
    instructions = build_interviewer_instructions(
        interview_type,
        language,
        has_resume=documents.resume is not None,
        has_references=bool(documents.references),
        role=role,
        seniority=seniority,
    )
    try:
        answer_sdp, live_session_id = await live_session.create_live_session(
            live_session.build_session_config(instructions), sdp
        )
        control = await live_control.attach_control(live_session_id, session.notify)
    except live_session.LiveUnavailableError:
        return _error(503, "OPENAI_UNAVAILABLE", _START_FAILED)

    # The stage could have changed while we waited on OpenAI (a second click).
    if not session.interview.uploads_allowed:
        await control.close()
        return _error(409, "INTERVIEW_STARTED", "The interview has already started.")

    session.interview.start(interview_type, language, role=role, seniority=seniority)
    session.live = control
    await conductor.send_stage(session)
    session.conductor_task = asyncio.create_task(conductor.run(session, control))
    logger.info("Interview %s started (%s, %s)", session.interview.interview_id, interview_type, language)

    return JSONResponse(
        {"sdp": answer_sdp, "live_session_id": live_session_id, "interview_id": session.interview.interview_id},
        status_code=201,
    )
