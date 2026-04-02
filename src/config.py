"""
Application configuration — loads all settings from .env via python-dotenv.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Language Model ────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# ─── Speech-to-Text ────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base.en")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ─── Text-to-Speech ────────────────────────────────────────────────────────────
MACOS_TTS_VOICE: str = os.getenv("MACOS_TTS_VOICE", "Samantha")
TTS_BACKEND: str = os.getenv("TTS_BACKEND", "auto")  # auto | espeak

# ─── Application ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")

# Ollama OpenAI-compatible endpoint
OLLAMA_API_BASE: str = f"{OLLAMA_BASE_URL.rstrip('/')}/v1"
