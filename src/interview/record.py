"""
Interview record — the questions and answers saved to disk during the
interview (FR-020, FR-022; specs/002-gpt-live-interview/data-model.md).

`close_answer()` is the one place the question/answer boundary rule lives
(research.md §5). Files go to `config.INTERVIEWS_DIR / interview_id`, read at
call time, and every write is atomic (temp file + os.replace).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from src import config
from src.interview.state import Interview, InterviewQuestion


# The interviewer can start saying a question slightly before the commentary's
# timeline mark, so the spoken wording looks back this far (answers don't).
SPOKEN_LEAD_MS = 1500


@dataclass(frozen=True)
class TranscriptFragment:
    speaker: Literal["user", "interviewer"]
    text: str
    start_ms: int
    end_ms: int


def _join(fragments: list[TranscriptFragment]) -> str:
    # Deltas carry their own spacing ("Hello there", ",", " this"): concatenate, then tidy.
    return " ".join("".join(f.text for f in fragments).split())


def close_answer(
    question: InterviewQuestion,
    fragments: list[TranscriptFragment],
    until_ms: float,
) -> tuple[str, str]:
    """
    The answer to `question` and what the interviewer said when asking it.

    The window runs from the question's `asked_at_ms` up to `until_ms`. The answer is
    every user fragment in it; the spoken question is the interviewer's fragments
    from just before `asked_at_ms` (SPOKEN_LEAD_MS) to the first user fragment. Both are
    ordered by start time.
    """
    window = sorted(
        (f for f in fragments if question.asked_at_ms <= f.start_ms < until_ms),
        key=lambda f: f.start_ms,
    )
    user = [f for f in window if f.speaker == "user"]
    first_user_ms = user[0].start_ms if user else until_ms
    spoken = sorted(
        (f for f in fragments
         if f.speaker == "interviewer" and question.asked_at_ms - SPOKEN_LEAD_MS <= f.start_ms < min(first_user_ms, until_ms)),
        key=lambda f: f.start_ms,
    )
    return _join(user), _join(spoken)


@dataclass
class InterviewRecord:
    interview_id: str
    interview_type: Literal["hr", "technical"]
    language: Literal["en", "pt-BR"]
    started_at: str
    ended_at: str | None = None
    end_reason: str | None = None
    report_status: Literal["none", "pending", "ready", "failed", "skipped"] = "none"
    role: str | None = None
    seniority: str = "mid"
    resume_filename: str | None = None
    reference_filenames: list[str] = field(default_factory=list)
    # Only questions whose answer window closed.
    questions: list[dict] = field(default_factory=list)

    @property
    def folder(self) -> Path:
        return config.INTERVIEWS_DIR / self.interview_id

    @property
    def answered(self) -> list[dict]:
        return [q for q in self.questions if (q.get("answer_text") or "").strip()]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def record_from_interview(interview: Interview, documents, started_at: str | None = None) -> InterviewRecord:
    """A record for this interview. Stores document filenames only, never their contents."""
    return InterviewRecord(
        interview_id=interview.interview_id,
        interview_type=interview.interview_type,
        language=interview.language or "en",
        role=interview.role,
        seniority=interview.seniority,
        started_at=started_at or now_iso(),
        resume_filename=documents.resume.filename if documents.resume else None,
        reference_filenames=[d.filename for d in documents.references],
    )


def question_entry(question: InterviewQuestion) -> dict:
    return {
        "index": question.index,
        "text": question.text,
        "spoken_text": question.spoken_text,
        "is_follow_up": question.is_follow_up,
        "answer_text": question.answer_text,
        "answered_at": question.answered_at.isoformat(timespec="seconds") if question.answered_at else None,
    }


# ── Rendering ─────────────────────────────────────────────────────────────────

TRANSCRIPT_LABELS = {
    "en": {"title": "Interview transcript", "hr": "HR interview", "technical": "Technical interview",
           "no_answer": "(no answer)", "started": "Started", "ended": "Ended",
           "junior": "Junior", "mid": "Mid-level", "senior": "Senior"},
    "pt-BR": {"title": "Transcrição da entrevista", "hr": "Entrevista de RH", "technical": "Entrevista técnica",
              "no_answer": "(sem resposta)", "started": "Início", "ended": "Fim",
              "junior": "Júnior", "mid": "Pleno", "senior": "Sênior"},
}


def position_line(record: "InterviewRecord", labels: dict) -> str:
    """'Senior · Backend Engineer' (or just the level when no role was given)."""
    level = labels.get(record.seniority, record.seniority)
    return f"{level} · {record.role}" if record.role else level


def render_transcript_md(record: InterviewRecord) -> str:
    labels = TRANSCRIPT_LABELS.get(record.language, TRANSCRIPT_LABELS["en"])
    lines = [
        f"# {labels['title']}",
        "",
        f"{labels[record.interview_type]} · {position_line(record, labels)} · {labels['started']}: {record.started_at}"
        + (f" · {labels['ended']}: {record.ended_at}" if record.ended_at else ""),
        "",
    ]
    for q in record.questions:
        answer = (q.get("answer_text") or "").strip() or labels["no_answer"]
        lines += [f"**Q{q['index']}.** {q['text']}", "", f"> {answer}", ""]
    return "\n".join(lines).rstrip() + "\n"


# ── Files ─────────────────────────────────────────────────────────────────────

def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_record(record: InterviewRecord) -> None:
    """Write record.json and transcript.md for this interview."""
    write_atomic(record.folder / "record.json", json.dumps(asdict(record), indent=2, ensure_ascii=False))
    write_atomic(record.folder / "transcript.md", render_transcript_md(record))


def load_record(interview_id: str) -> InterviewRecord | None:
    path = config.INTERVIEWS_DIR / interview_id / "record.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # Records saved before 003 have no role/seniority: the dataclass defaults cover them.
    known = InterviewRecord.__dataclass_fields__
    return InterviewRecord(**{k: v for k, v in data.items() if k in known})
