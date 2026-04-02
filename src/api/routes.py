"""
HTTP routes: health check and static file serving.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()

FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "model_loaded": True})


def mount_static(app) -> None:
    """Mount frontend/dist/ as static files (SPA fallback)."""
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
