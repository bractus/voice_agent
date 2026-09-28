"""
HTTP routes: health check, OpenAI status, and static file serving.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src import openai_client

router = APIRouter()

FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "openai": await openai_client.check_openai()})


@router.get("/api/status")
async def status() -> JSONResponse:
    """Whether the interviewer can start (contracts/http-api.md)."""
    openai_status = await openai_client.check_openai()
    return JSONResponse({"openai": openai_status, "message": openai_client.STATUS_MESSAGES[openai_status]})


def mount_static(app) -> None:
    """Mount frontend/dist/ as static files (SPA fallback)."""
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
