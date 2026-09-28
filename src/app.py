from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Voice Fairy — mock-interview server (FastAPI).

Serves the React frontend, the HTTP API and the app WebSocket. Interview audio
flows over WebRTC between the browser and OpenAI GPT-Live; this server creates
those sessions and steers them.

Run:
    python src/app.py
    # or
    API_PORT=8000 python src/app.py

Open http://localhost:8000 in a browser and grant microphone permission.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.config import API_HOST, API_PORT, LOG_LEVEL
from src.api.session_manager import session_manager
from src.api.websocket import router as ws_router
from src.api.documents import router as documents_router
from src.api.interviews import router as interviews_router
from src.api.live import router as live_router
from src.api.routes import router as http_router, mount_static

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # No billed GPT-Live session may outlive the app (research.md §12).
    for session in session_manager.all():
        await session.shutdown()


app = FastAPI(title="Voice Fairy", lifespan=lifespan)

app.include_router(ws_router)
app.include_router(documents_router)
app.include_router(live_router)
app.include_router(interviews_router)
app.include_router(http_router)
mount_static(app)

if __name__ == "__main__":
    logger.info("Starting Voice Fairy on http://%s:%d", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT)
