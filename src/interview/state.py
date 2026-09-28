"""
Interview state — the stage machine that drives a mock interview.

Stages and their allowed transitions are documented in
specs/002-gpt-live-interview/data-model.md. Each transition method checks
the current stage and raises InvalidStageError when the move isn't allowed.
"""
from __future__ import annotations

import random
import string
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

from src.config import SUPPORTED_LANGUAGES

InterviewType = Literal["hr", "technical"]
InterviewLanguage = Literal["en", "pt-BR"]
EndReason = Literal["user_request", "end_button", "inactivity", "connection_lost", "page_closed"]
Seniority = Literal["junior", "mid", "senior"]

INTERVIEW_TYPES: tuple[str, ...] = ("hr", "technical")
SENIORITIES: tuple[str, ...] = ("junior", "mid", "senior")
ROLE_MAX_CHARS = 80


def normalise_role(raw: object) -> str | None:
    """Trim, drop control characters and collapse whitespace; None when nothing is left."""
    if not isinstance(raw, str):
        return None
    text = "".join(c if unicodedata.category(c)[0] != "C" else " " for c in raw)
    text = " ".join(text.split())
    return text or None


class InterviewStage(str, Enum):
    SETUP = "setup"
    INTRODUCING = "introducing"
    INTERVIEWING = "interviewing"
    CONCLUDING = "concluding"
    CONCLUDED = "concluded"


class ReportStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvalidStageError(Exception):
    """Raised when a transition is attempted from a stage that doesn't allow it."""


@dataclass
class InterviewQuestion:
    index: int                        # 1-based
    text: str                         # canonical: the question writer's output
    asked_at_ms: int                  # session timeline; opens the answer window
    spoken_text: str = ""             # what the interviewer actually said
    is_follow_up: bool = False        # always False for HR
    grounded_chunk_ids: list[int] = field(default_factory=list)
    answer_text: str | None = None    # None while the answer window is open
    answered_at: datetime | None = None


def _new_interview_id(interview_type: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{datetime.now():%Y%m%d-%H%M%S}-{interview_type}-{suffix}"


@dataclass
class Interview:
    stage: InterviewStage = InterviewStage.SETUP
    interview_type: InterviewType | None = None      # None only in setup
    language: InterviewLanguage | None = None        # None only in setup
    role: str | None = None                          # candidate's text, ≤ 80 chars (003 FR-001)
    seniority: Seniority = "mid"                     # 003 FR-002
    interview_id: str | None = None
    questions: list[InterviewQuestion] = field(default_factory=list)
    used_chunk_ids: set[int] = field(default_factory=set)
    pending_delegation_id: str | None = None
    prefetched_question: str | None = None
    report_status: ReportStatus = ReportStatus.NONE
    end_reason: EndReason | None = None
    last_speech_at: float = 0.0
    checked_in_since_user_spoke: bool = False

    # ── Transitions ───────────────────────────────────────────────────────────

    def start(
        self,
        interview_type: str,
        language: str = "en",
        role: str | None = None,
        seniority: str = "mid",
    ) -> None:
        """setup → introducing. Type, language, role and seniority are fixed from here on."""
        if interview_type not in INTERVIEW_TYPES:
            raise ValueError(f"Unknown interview type: {interview_type!r}")
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported interview language: {language!r}")
        if seniority not in SENIORITIES:
            raise ValueError(f"Unknown seniority: {seniority!r}")
        role = normalise_role(role)
        if role is not None and len(role) > ROLE_MAX_CHARS:
            raise ValueError(f"Role longer than {ROLE_MAX_CHARS} characters")
        self._require(InterviewStage.SETUP)
        self.interview_type = interview_type  # type: ignore[assignment]
        self.language = language  # type: ignore[assignment]
        self.role = role
        self.seniority = seniority  # type: ignore[assignment]
        self.interview_id = _new_interview_id(interview_type)
        self.stage = InterviewStage.INTRODUCING

    def begin_interviewing(self) -> None:
        """introducing → interviewing (the first question was requested)."""
        self._require(InterviewStage.INTRODUCING)
        self.stage = InterviewStage.INTERVIEWING

    def request_end(self, reason: EndReason) -> None:
        """introducing | interviewing → concluding."""
        self._require(InterviewStage.INTRODUCING, InterviewStage.INTERVIEWING)
        self.end_reason = reason
        self.stage = InterviewStage.CONCLUDING

    def finish(self) -> None:
        """concluding → concluded."""
        self._require(InterviewStage.CONCLUDING)
        self.stage = InterviewStage.CONCLUDED

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def uploads_allowed(self) -> bool:
        return self.stage == InterviewStage.SETUP

    @property
    def is_active(self) -> bool:
        return self.stage in (InterviewStage.INTRODUCING, InterviewStage.INTERVIEWING)

    @property
    def current_question(self) -> InterviewQuestion | None:
        return self.questions[-1] if self.questions else None

    def _require(self, *allowed: InterviewStage) -> None:
        if self.stage not in allowed:
            names = ", ".join(s.value for s in allowed)
            raise InvalidStageError(f"Expected stage {names}, but interview is in {self.stage.value}")
