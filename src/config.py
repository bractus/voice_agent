"""
Application configuration — loads all settings from src/.env (and a root .env, if any) via python-dotenv.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# src/.env holds OPENAI_API_KEY; load it explicitly so it's found however the app is started.
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

# ─── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_LIVE_MODEL: str = os.getenv("OPENAI_LIVE_MODEL", "gpt-live-1")
OPENAI_LIVE_VOICE: str = os.getenv("OPENAI_LIVE_VOICE", "marin")
OPENAI_QUESTION_MODEL: str = os.getenv("OPENAI_QUESTION_MODEL", "gpt-6-luna")
OPENAI_EVALUATOR_MODEL: str = os.getenv("OPENAI_EVALUATOR_MODEL", "gpt-6-sol")
OPENAI_EMBED_MODEL: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
LIVE_CONTROL: str = os.getenv("LIVE_CONTROL", "sideband")  # sideband | browser_relay (research.md §1)

# ─── OpenRouter (the feedback grader) ──────────────────────────────────────────
# Jev is a decisions model: it grades and checks answers, and can't write text (specs/004 research.md §1).
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_GRADER_MODEL: str = os.getenv("OPENROUTER_GRADER_MODEL", "~typesafe/jev-latest")

# ─── Interview ─────────────────────────────────────────────────────────────────
# Read as `config.INTERVIEWS_DIR` at call time, so tests can patch this one attribute.
INTERVIEWS_DIR: Path = Path(os.getenv("INTERVIEWS_DIR", Path(__file__).resolve().parent.parent / "interviews"))
# Silence from both sides that ends the interview (FR-025).
INACTIVITY_END_SECONDS: int = int(os.getenv("INACTIVITY_END_SECONDS", "180"))
# Quiet after the candidate speaks before the interviewer is told they seem to have finished (research.md §7).
ANSWER_END_SILENCE_SECONDS: float = float(os.getenv("ANSWER_END_SILENCE_SECONDS", "4"))
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "pt-BR")
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "pt-BR": "Brazilian Portuguese"}

# ─── Documents (resume + reference material) ───────────────────────────────────
RESUME_MAX_BYTES: int = 5 * 1024 * 1024
REFERENCE_MAX_FILES: int = 5
REFERENCE_MAX_BYTES: int = 20 * 1024 * 1024
# Cost/time guard for OpenAI embeddings (~2.4M tokens ≈ $0.05); provisional, see research.md §10.
REFERENCE_MAX_CHUNKS: int = int(os.getenv("REFERENCE_MAX_CHUNKS", "8000"))
# A document yielding less text than this is treated as unreadable.
MIN_EXTRACTED_CHARS: int = 200
# How much of the resume goes into the interviewer prompt.
RESUME_PROMPT_MAX_CHARS: int = 12_000

# ─── Application ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")

