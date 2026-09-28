"""
Question writer — the subagent that writes each next interview question
(specs/002-gpt-live-interview/contracts/agents.md#question-writer).

`build_question_request()` is pure and decides what the writer may see. HR
requests never contain an answer, which is what keeps HR free of follow-ups
(FR-020 of 001). `write_question()` calls the model, cleans the output, and
regenerates once if it repeats an earlier question.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field

from src import config
from src.documents.errors import EmbeddingUnavailableError
from src.documents.store import DocumentSet
from src.interview import prompts
from src.interview.state import Interview
from src.openai_client import describe_error, get_async_client

logger = logging.getLogger(__name__)

# Near-identical questions (FR-019 of 001) — see 001 research.md §8.
_DUPLICATE_RATIO = 0.9
# Reference passages retrieved per technical question.
_RETRIEVAL_TOP_K = 4
# Search query for the first question, before there is an answer to search with.
_FIRST_QUESTION_QUERY = "the main topics and key concepts covered in this material"
# Reasoning tokens count toward this limit too, so it's well above the question's length.
_MAX_OUTPUT_TOKENS = 1024

_FOLLOW_UP_PREFIX = re.compile(r"^\s*follow[\s-]?up\s*:\s*", re.IGNORECASE)
_SPEAKER_LABEL = re.compile(r"^(interviewer|assistant|question|pergunta|entrevistador)\s*:\s*", re.IGNORECASE)


class QuestionUnavailableError(Exception):
    """The question writer failed twice for one question."""


@dataclass
class QuestionRequest:
    interview_type: str
    language: str
    resume_text: str | None
    passages: list[str] = field(default_factory=list)
    passage_ids: list[int] = field(default_factory=list)
    questions_asked: list[str] = field(default_factory=list)
    last_exchange: dict | None = None
    role: str | None = None
    seniority: str = "mid"


@dataclass
class QuestionResult:
    text: str
    is_follow_up: bool
    grounded_chunk_ids: list[int]


def _retrieve(interview: Interview, documents: DocumentSet) -> list[int]:
    index = documents.index
    if interview.interview_type != "technical" or index is None or not len(index):
        return []
    last = interview.current_question
    query = f"{last.text} {last.answer_text or ''}".strip() if last else _FIRST_QUESTION_QUERY
    try:
        return index.search(query, k=_RETRIEVAL_TOP_K, exclude=interview.used_chunk_ids)
    except EmbeddingUnavailableError as exc:
        # Ask a question anyway, just without grounding.
        logger.warning("Retrieval skipped: %s", exc.message)
        return []


def build_question_request(interview: Interview, documents: DocumentSet) -> QuestionRequest:
    """What the question writer gets for the next question (pure apart from the index search)."""
    technical = interview.interview_type == "technical"
    passage_ids = _retrieve(interview, documents) if technical else []
    last = interview.current_question
    return QuestionRequest(
        interview_type=interview.interview_type,
        language=interview.language or "en",
        resume_text=documents.resume.text[:config.RESUME_PROMPT_MAX_CHARS] if documents.resume else None,
        passages=documents.chunk_texts(passage_ids),
        passage_ids=passage_ids,
        questions_asked=[q.text for q in interview.questions],
        role=interview.role,
        seniority=interview.seniority,
        # HR never sees answers (FR-020 of 001).
        last_exchange=(
            {"question": last.text, "answer": last.answer_text}
            if technical and last is not None and last.answer_text
            else None
        ),
    )


def clean_question(raw: str | None) -> tuple[str, bool]:
    """Strip quotes, labels and whitespace; detect and strip the FOLLOW-UP: marker."""
    text = (raw or "").strip().strip('"“”').strip()
    text = _SPEAKER_LABEL.sub("", text).strip().strip('"“”').strip()
    is_follow_up = bool(_FOLLOW_UP_PREFIX.match(text))
    text = _FOLLOW_UP_PREFIX.sub("", text).strip().strip('"“”').strip()
    return text, is_follow_up


def is_duplicate(candidate: str, asked: list[str]) -> bool:
    candidate = candidate.lower()
    return any(difflib.SequenceMatcher(None, candidate, q.lower()).ratio() >= _DUPLICATE_RATIO for q in asked)


async def _call_model(request: QuestionRequest, nudge: bool) -> str:
    instructions = prompts.build_question_writer_prompt(
        request.interview_type,
        request.language,
        resume_text=request.resume_text,
        reference_context=request.passages,
        questions_asked=request.questions_asked,
        last_exchange=request.last_exchange,
        role=request.role,
        seniority=request.seniority,
    )
    user_input = "Write the next question."
    if nudge:
        user_input += " " + prompts.REPEAT_NUDGE
    response = await get_async_client().responses.create(
        model=config.OPENAI_QUESTION_MODEL,
        instructions=instructions,
        input=user_input,
        reasoning={"effort": "low"},
        max_output_tokens=_MAX_OUTPUT_TOKENS,
    )
    if response.status != "completed":
        # A cut-off question must never be spoken.
        raise RuntimeError(f"question writer response {response.status}")
    return response.output_text


async def write_question(interview: Interview, documents: DocumentSet) -> QuestionResult:
    """Write the next question, regenerating once if it's empty or repeats an earlier one."""
    request = build_question_request(interview, documents)
    for attempt in range(2):
        try:
            raw = await _call_model(request, nudge=attempt > 0)
        except Exception as exc:
            logger.warning("Question writer call failed (attempt %d): %s", attempt + 1, describe_error(exc))
            continue
        text, follow_up = clean_question(raw)
        if not text or is_duplicate(text, request.questions_asked):
            logger.info("Question writer returned an empty or repeated question; retrying")
            continue
        return QuestionResult(
            text=text,
            is_follow_up=follow_up and request.interview_type == "technical",
            grounded_chunk_ids=request.passage_ids,
        )
    raise QuestionUnavailableError("The next question couldn't be written.")
