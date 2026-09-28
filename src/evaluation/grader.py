"""
The grader: Jev, a decisions model on OpenRouter (specs/004-exact-answer-feedback/contracts/grader.md).

One call grades one answer, either the candidate's or a model answer. It returns the
score from 0 to 5 as Jev gives it, the most likely level, and the diagnostics the answer
fails (its gaps). Jev can't write text, so the writer turns this into feedback.

Anything unexpected (no key, a rejected key, a timeout, a 5xx or a malformed reply after
one retry) raises GraderUnavailableError, and the evaluation falls back to the writer's
own grades rather than failing (research.md §7).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx

from src import config
from src.evaluation.prompts import GRADE_LEVELS, NO_ANSWER, build_grade_instructions, diagnostics_for
from src.interview.prompts import describe_position
from src.interview.record import InterviewRecord
from src.openrouter_client import describe_http_error, get_openrouter_client

logger = logging.getLogger(__name__)

DECISIONS_PATH = "/api/alpha/decisions"
GRADER_TIMEOUT_SECONDS = 10.0   # patched in tests
GAP_THRESHOLD = 0.5             # a diagnostic below this is a gap
_NO_RETRY = {400, 401, 402, 403, 404}
LEVELS = range(len(GRADE_LEVELS))


class GraderUnavailableError(Exception):
    """The grader couldn't grade (after its retry). The message never contains the key."""


@dataclass(frozen=True)
class GraderResult:
    score: float                         # as returned, 0–5
    level: int                           # the most likely level (argmax of probabilities)
    probabilities: dict[int, float]
    confidence: float | None
    gaps: list[str] = field(default_factory=list)
    model: str = ""


def build_grade_request(
    record: InterviewRecord,
    question: dict,
    answer_text: str,
    passages: Sequence[str] = (),
) -> dict:
    state: dict = {
        "interview": "HR (behavioral)" if record.interview_type == "hr" else "technical",
        "position": describe_position(record.role, record.seniority),
        "question": question["text"],
        "answer": answer_text.strip() or NO_ANSWER,
    }
    if passages:
        state["reference_passages"] = [p.strip() for p in passages]
    questions: dict = {
        "grade": {"type": "score", "instructions": build_grade_instructions(record), "criteria": GRADE_LEVELS},
    }
    for check_id, text in diagnostics_for(record, bool(passages)).items():
        questions[check_id] = {"type": "noul", "instructions": text, "criteria": {"true": "Yes", "false": "No"}}
    return {"model": config.OPENROUTER_GRADER_MODEL, "state": state, "questions": questions}


def _number(value, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise GraderUnavailableError(f"value out of range: {value!r}")
    return float(value)


def parse_grade_response(data: dict, diagnostic_ids: Sequence[str]) -> GraderResult:
    """Validate the reply and read the grade. Raises GraderUnavailableError on anything unexpected."""
    try:
        answers = data["answers"]
        grade = answers["grade"]
        if grade.get("type") != "score":
            raise GraderUnavailableError("the grade isn't a score answer")
        score = _number(grade["score"], 0, len(GRADE_LEVELS) - 1)
        probabilities = {int(k): _number(v, 0, 1) for k, v in grade["probabilities"].items()}
        if set(probabilities) != set(LEVELS):
            raise GraderUnavailableError("probabilities don't cover every level")
        confidence = grade.get("confidence")
        confidence = _number(confidence, 0, 1) if confidence is not None else None
        gaps = [i for i in diagnostic_ids if _number(answers[i]["noul"], 0, 1) < GAP_THRESHOLD]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise GraderUnavailableError(f"malformed grader reply: {type(exc).__name__}") from None
    # Ties go to the lower level: "5/5" has to be clearly the most likely.
    level = max(LEVELS, key=lambda k: (probabilities[k], -k))
    return GraderResult(score, level, probabilities, confidence, gaps, str(data.get("model", "")))


async def grade_answer(
    record: InterviewRecord,
    question: dict,
    answer_text: str,
    passages: Sequence[str] = (),
) -> GraderResult:
    """Grade one answer. One retry on a timeout, a 5xx, a 429 or a malformed reply."""
    if not config.OPENROUTER_API_KEY:
        raise GraderUnavailableError("no OpenRouter key is configured")
    body = build_grade_request(record, question, answer_text, passages)
    diagnostic_ids = [k for k in body["questions"] if k != "grade"]
    for attempt in (1, 2):
        try:
            response = await get_openrouter_client().post(DECISIONS_PATH, json=body, timeout=GRADER_TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            logger.warning("Grader call failed (attempt %d): %s", attempt, describe_http_error(exc))
            continue
        if response.status_code in _NO_RETRY:
            logger.warning("Grader rejected the request: HTTP %d", response.status_code)
            raise GraderUnavailableError(f"the grader rejected the request (HTTP {response.status_code})")
        if response.status_code >= 400:
            logger.warning("Grader call failed (attempt %d): HTTP %d", attempt, response.status_code)
            continue
        try:
            data = response.json()
            result = parse_grade_response(data, diagnostic_ids)
        except (ValueError, GraderUnavailableError) as exc:
            logger.warning("Grader reply rejected (attempt %d): %s", attempt, type(exc).__name__)
            continue
        logger.debug("Graded question %s: %.2f (cost %s)", question.get("index"), result.score,
                     (data.get("usage") or {}).get("cost"))
        return result
    raise GraderUnavailableError("the grader didn't answer after a retry")
