"""
Evaluator — writes the feedback report after an interview ends (specs/004-exact-answer-feedback).

Two models work together (research.md §2–§8):
1. the grader (Jev) scores every candidate answer, one call each, in parallel;
2. the writer writes what worked, what was missing and the exact 5/5 answer per question,
   in parallel, plus the overall section;
3. the grader checks every 5/5 answer; one that isn't at level 5 is rewritten once, and
   the version with the higher score is kept.

If the grader is unavailable, the whole report falls back to the writer's own grades on
the same 0–5 scale (`grader: "writer"`), with no checks. The output is validated against
the record (format 2, data-model.md). A writer call that fails twice fails the evaluation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable

from src import config
from src.evaluation.grader import GraderResult, GraderUnavailableError, grade_answer
from src.evaluation.prompts import (
    GAP_DESCRIPTIONS,
    MODEL_ANSWER_INSTRUCTIONS,
    OVERALL_INSTRUCTIONS,
    OVERALL_SCHEMA,
    REWRITE_INSTRUCTIONS,
    REWRITE_SCHEMA,
    GradeSummary,
    build_overall_input,
    build_question_input,
    build_rewrite_input,
    question_schema,
)
from src.interview.record import InterviewRecord
from src.openai_client import describe_error, get_async_client

logger = logging.getLogger(__name__)

MAX_WRITER_CALLS = 8
MAX_GRADER_CALLS = 16
MAX_MODEL_ANSWER_WORDS = 260
TOP_LEVEL = 5
_LIST_LINE = re.compile(r"^\s*(?:[-*]|#+|\d+[.)])\s", re.MULTILINE)


class EvaluationFailedError(Exception):
    """The evaluation couldn't be written."""


class InvalidReportError(ValueError):
    pass


# ── Validation ────────────────────────────────────────────────────────────────

def _text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReportError(f"{what} must be non-empty text")
    return value


def _in_range(value, low: float, high: float, what: str, integer: bool = False) -> None:
    kinds = (int,) if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, kinds) or not low <= value <= high:
        raise InvalidReportError(f"{what} out of range: {value!r}")


def _check_model_answer(text) -> str:
    text = _text(text, "model_answer")
    if len(text.split()) > MAX_MODEL_ANSWER_WORDS:
        raise InvalidReportError(f"model_answer is longer than {MAX_MODEL_ANSWER_WORDS} words")
    if _LIST_LINE.search(text):
        raise InvalidReportError("model_answer contains a list or heading line")
    return text


def validate_question_feedback(item: dict) -> dict:
    """One `per_question` entry of a format 2 report."""
    try:
        _in_range(item["index"], 1, float("inf"), "index", integer=True)
        _in_range(item["score"], 0, 5, "score")
        _in_range(item["level"], 0, 5, "level", integer=True)
        _text(item["what_worked"], "what_worked")
        _text(item["missing"], "missing")
        _check_model_answer(item["model_answer"])
        check = item["model_answer_check"]
        if check is not None:
            if not isinstance(check.get("passed"), bool) or not isinstance(check.get("rewritten"), bool):
                raise InvalidReportError("model_answer_check needs passed and rewritten")
            _in_range(check["score"], 0, 5, "check score")
            _in_range(check["level"], 0, 5, "check level", integer=True)
    except (KeyError, TypeError, AttributeError) as exc:
        raise InvalidReportError(f"malformed entry: {exc!r}") from exc
    return item


def _validate_overall(overall: dict) -> dict:
    try:
        if not isinstance(overall["summary"], str):
            raise InvalidReportError("summary must be text")
        if not all(isinstance(s, str) for s in overall["strengths"]):
            raise InvalidReportError("strengths must be text")
        for area in overall["areas_to_improve"]:
            if not isinstance(area, dict) or not isinstance(area["text"], str):
                raise InvalidReportError("areas_to_improve entries need text")
            if not all(isinstance(i, int) and not isinstance(i, bool) for i in area["questions"]):
                raise InvalidReportError("areas_to_improve questions must be integers")
    except (KeyError, TypeError) as exc:
        raise InvalidReportError(f"malformed overall: {exc!r}") from exc
    return overall


def validate_report(data: dict, record: InterviewRecord) -> dict:
    """Check a format 2 report against the record. Returns it, or raises InvalidReportError."""
    try:
        per_question = data["per_question"]
        for item in per_question:
            validate_question_feedback(item)
        _validate_overall(data["overall"])
        indexes = sorted(item["index"] for item in per_question)
    except (KeyError, TypeError) as exc:
        raise InvalidReportError(f"malformed report: {exc!r}") from exc
    expected = sorted(q["index"] for q in record.questions)
    if indexes != expected:
        raise InvalidReportError(f"question indexes {indexes} don't match the record {expected}")
    return data


def _check_feedback(data: dict, with_rating: bool) -> dict:
    try:
        _text(data["what_worked"], "what_worked")
        _text(data["missing"], "missing")
        _check_model_answer(data["model_answer"])
        if with_rating:
            _in_range(data["rating"], 0, 5, "rating", integer=True)
    except (KeyError, TypeError) as exc:
        raise InvalidReportError(f"malformed feedback: {exc!r}") from exc
    return data


def _check_rewrite(data: dict) -> dict:
    try:
        _check_model_answer(data["model_answer"])
    except (KeyError, TypeError) as exc:
        raise InvalidReportError(f"malformed rewrite: {exc!r}") from exc
    return data


# ── Model calls ───────────────────────────────────────────────────────────────

async def _call_writer(name: str, instructions: str, input_text: str, schema: dict) -> dict:
    """One writer call: the Responses API with a strict JSON schema. Patched in tests."""
    response = await get_async_client().responses.create(
        model=config.OPENAI_EVALUATOR_MODEL,
        instructions=instructions,
        input=input_text,
        reasoning={"effort": "medium"},
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
    )
    return json.loads(response.output_text)


async def _write(
    name: str,
    instructions: str,
    input_text: str,
    schema: dict,
    check: Callable[[dict], dict],
    semaphore: asyncio.Semaphore,
) -> dict:
    """A writer call with one retry on an invalid output or an API error."""
    for attempt in (1, 2):
        try:
            async with semaphore:
                data = await _call_writer(name, instructions, input_text, schema)
            return check(data)
        except InvalidReportError as exc:
            logger.warning("Writer output rejected (%s, attempt %d): %s", name, attempt, exc)
        except Exception as exc:
            logger.warning("Writer call failed (%s, attempt %d): %s", name, attempt, describe_error(exc))
    raise EvaluationFailedError(f"The {name} couldn't be written.")


def _summary(result: GraderResult) -> GradeSummary:
    return GradeSummary(result.score, result.level, [GAP_DESCRIPTIONS.get(g, g) for g in result.gaps])


async def _grade_all(record: InterviewRecord, answers: dict[int, str], passages: dict[int, list[str]],
                     semaphore: asyncio.Semaphore) -> dict[int, GraderResult | Exception]:
    """Grade several answers in parallel. Failures come back as exceptions, not raised."""
    by_index = {q["index"]: q for q in record.questions}

    async def one(index: int) -> GraderResult:
        async with semaphore:
            return await grade_answer(record, by_index[index], answers[index], passages.get(index, []))

    indexes = list(answers)
    results = await asyncio.gather(*(one(i) for i in indexes), return_exceptions=True)
    return dict(zip(indexes, results))


# ── The evaluation ────────────────────────────────────────────────────────────

async def run_evaluation(
    record: InterviewRecord,
    resume_text: str | None = None,
    passages_by_index: dict[int, list[str]] | None = None,
) -> dict:
    """Grade, write, check and rewrite. Returns a validated format 2 report (without the record fields)."""
    passages = passages_by_index or {}
    questions = record.questions
    writer_sem = asyncio.Semaphore(MAX_WRITER_CALLS)
    grader_sem = asyncio.Semaphore(MAX_GRADER_CALLS)

    # 1. Grade every candidate answer. Any failure: the whole report falls back to the writer.
    grades: dict[int, GraderResult] | None = None
    if config.OPENROUTER_API_KEY:
        graded = await _grade_all(record, {q["index"]: q.get("answer_text") or "" for q in questions}, passages, grader_sem)
        failures = [r for r in graded.values() if isinstance(r, BaseException)]
        if failures:
            logger.warning("Grader unavailable (%s); the writer grades this report", type(failures[0]).__name__)
        else:
            grades = graded  # type: ignore[assignment]
    else:
        logger.info("No OpenRouter key; the writer grades this report")
    summaries = {i: _summary(r) for i, r in grades.items()} if grades else None

    # 2. Write the feedback per question, and the overall section, all in parallel.
    with_rating = grades is None
    feedback_calls = [
        _write(
            "question_feedback", MODEL_ANSWER_INSTRUCTIONS,
            build_question_input(record, q, resume_text, passages.get(q["index"], []),
                                 summaries[q["index"]] if summaries else None),
            question_schema(with_rating), lambda d: _check_feedback(d, with_rating), writer_sem,
        )
        for q in questions
    ]
    overall_call = _write("overall", OVERALL_INSTRUCTIONS, build_overall_input(record, resume_text, summaries),
                          OVERALL_SCHEMA, _validate_overall, writer_sem)
    results = await asyncio.gather(*feedback_calls, overall_call, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            if isinstance(result, EvaluationFailedError):
                raise result
            raise EvaluationFailedError("The evaluation couldn't be written.") from result
    feedback = {q["index"]: fb for q, fb in zip(questions, results[:-1])}
    overall = results[-1]

    # 3. Check every 5/5 answer; rewrite the ones that don't reach the top level, once.
    checks: dict[int, dict | None] = {q["index"]: None for q in questions}
    if grades is not None:
        checks = await _check_and_rewrite(record, resume_text, passages, summaries, feedback, writer_sem, grader_sem)

    per_question = []
    for q in questions:
        index, fb = q["index"], feedback[q["index"]]
        score, level = (grades[index].score, grades[index].level) if grades else (float(fb["rating"]), fb["rating"])
        per_question.append({
            "index": index,
            "score": score,
            "level": level,
            "what_worked": fb["what_worked"],
            "missing": fb["missing"],
            "model_answer": fb["model_answer"],
            "model_answer_check": checks[index],
        })

    known = {q["index"] for q in questions}
    overall["areas_to_improve"] = [
        {"text": area["text"], "questions": [i for i in area["questions"] if i in known]}
        for area in overall["areas_to_improve"]
    ]
    report = {
        "grader": "writer" if grades is None else "jev",
        "grader_model": (next(iter(grades.values())).model or None) if grades else None,
        "writer_model": config.OPENAI_EVALUATOR_MODEL,
        "per_question": per_question,
        "overall": overall,
    }
    try:
        return validate_report(report, record)
    except InvalidReportError as exc:
        raise EvaluationFailedError("The evaluation couldn't be validated.") from exc


async def _check_and_rewrite(
    record: InterviewRecord,
    resume_text: str | None,
    passages: dict[int, list[str]],
    summaries: dict[int, GradeSummary],
    feedback: dict[int, dict],
    writer_sem: asyncio.Semaphore,
    grader_sem: asyncio.Semaphore,
) -> dict[int, dict | None]:
    """Grade each model answer; rewrite the failing ones once. Updates `feedback` in place."""
    first = await _grade_all(record, {i: fb["model_answer"] for i, fb in feedback.items()}, passages, grader_sem)
    by_index = {q["index"]: q for q in record.questions}
    checks: dict[int, dict | None] = {}
    failing: list[int] = []
    for index, result in first.items():
        if isinstance(result, BaseException):
            logger.warning("Model answer %d couldn't be checked: %s", index, type(result).__name__)
            checks[index] = None
        else:
            checks[index] = {"passed": result.level == TOP_LEVEL, "score": result.score,
                             "level": result.level, "rewritten": False}
            if result.level != TOP_LEVEL:
                failing.append(index)
    if not failing:
        return checks

    async def rewrite(index: int) -> dict:
        result = first[index]
        return await _write(
            "model_answer_rewrite", REWRITE_INSTRUCTIONS,
            build_rewrite_input(record, by_index[index], resume_text, passages.get(index, []), summaries[index],
                                feedback[index]["model_answer"], _summary(result)),
            REWRITE_SCHEMA, _check_rewrite, writer_sem,
        )

    rewrites = await asyncio.gather(*(rewrite(i) for i in failing), return_exceptions=True)
    rewritten = {i: r["model_answer"] for i, r in zip(failing, rewrites) if not isinstance(r, BaseException)}
    for i, r in zip(failing, rewrites):
        if isinstance(r, BaseException):
            logger.warning("Model answer %d couldn't be rewritten: %s", i, type(r).__name__)
    if not rewritten:
        return checks

    second = await _grade_all(record, rewritten, passages, grader_sem)
    for index, result in second.items():
        if isinstance(result, BaseException):
            continue  # keep the checked first version
        # A version that passes beats one that doesn't; otherwise the higher score wins.
        before = checks[index]
        if (result.level == TOP_LEVEL, result.score) > (before["passed"], before["score"]):
            feedback[index]["model_answer"] = rewritten[index]
            checks[index] = {"passed": result.level == TOP_LEVEL, "score": result.score,
                             "level": result.level, "rewritten": True}
    logger.info("Rewrote %d model answer(s); %d now pass", len(rewritten),
                sum(1 for i in rewritten if checks[i] and checks[i]["passed"]))
    return checks
