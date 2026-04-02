from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Voice assistant — FastAPI + WebSocket server.

Serves the React frontend and exposes the WebSocket voice protocol.

Run:
    python src/app.py
    # or
    API_PORT=8000 python src/app.py

Open http://localhost:8000 in a browser and grant microphone permission.
"""

import logging

import uvicorn
from fastapi import FastAPI

from src.config import API_HOST, API_PORT, LOG_LEVEL
from src.api.websocket import router as ws_router
from src.api.routes import router as http_router, mount_static

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Fairy")

app.include_router(ws_router)
app.include_router(http_router)
mount_static(app)

if __name__ == "__main__":
    logger.info("Starting Voice Fairy on http://%s:%d", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT)
