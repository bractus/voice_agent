"""
What the feedback models are told (specs/004-exact-answer-feedback/contracts/).

Two models work together:
- the grader (Jev, a decisions model on OpenRouter) scores each answer from 0 to 5 and
  answers yes/no diagnostics; it can't write text (grader.md);
- the writer (the evaluator model) turns the grade and the gaps into what worked, what
  was missing and the exact 5/5 answer, per question, plus an overall section (agents.md).

Instructions are in English; the header fixes the language the writer writes in.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from src.config import LANGUAGE_NAMES
from src.interview.prompts import SENIORITY_GUIDE, SENIORITY_LABELS, describe_position
from src.interview.record import InterviewRecord

# The grader's rubric: six described levels, so its native score already runs from 0 to 5
# and is used as returned (research.md §2).
GRADE_LEVELS: list[str] = [
    "0 - no answer: the question was not answered at all",
    "1 - weak: vague or off-topic, no concrete content",
    "2 - below expectations: on topic but generic, missing key elements",
    "3 - adequate: answers the question with some concrete content, but gaps remain",
    "4 - good: concrete, well structured, only minor gaps",
    "5 - excellent: what a strong candidate at this level would say; nothing important missing",
]

NO_ANSWER = "(no answer)"


@dataclass(frozen=True)
class GradeSummary:
    """A grade as the writer sees it: the score, its level, and the gaps in plain words."""
    score: float
    level: int
    gaps: list[str] = field(default_factory=list)


def _kind(record: InterviewRecord) -> str:
    return "HR (behavioral)" if record.interview_type == "hr" else "technical"


def _answer(question: dict) -> str:
    return (question.get("answer_text") or "").strip() or NO_ANSWER


# ── Grader (Jev) ──────────────────────────────────────────────────────────────

# Yes/no diagnostics; a gap is a `noul` below 0.5 (research.md §4). Ids are part of the contract.
HR_DIAGNOSTICS: dict[str, str] = {
    "answers_exact_question": "Does the answer respond directly to the exact question asked, not a similar or broader one?",
    "concrete_situation": "Does it describe one specific, real situation (who, what, when), not a generic habit or a hypothetical?",
    "own_actions": "Does it make the candidate's own actions and decisions clear (I did X), not only the team's?",
    "measurable_result": "Does it state a concrete result, ideally with a number or an observable change?",
    "reflection": "Does it say what the candidate learned or would do differently?",
    "level_fit": "Does it show what is expected of a candidate at this level?",
}
TECH_DIAGNOSTICS: dict[str, str] = {
    "answers_exact_question": "Does the answer respond directly to the exact question asked, not a similar or broader one?",
    "correct": "Is what the answer says technically correct?",
    "depth": "Does it explain how or why it works, beyond naming the concept?",
    "trade_offs": "Does it discuss trade-offs, limits or alternatives?",
    "concrete_example": "Does it give a concrete example, ideally from the candidate's own experience?",
    "level_fit": "Does it show what is expected of a candidate at this level?",
}
CONSISTENT_WITH_REFERENCE = (
    "consistent_with_reference",
    "Is the answer consistent with the reference passages given in the state?",
)

# How each gap is described to the writer (in English; the writer writes in the interview language).
GAP_DESCRIPTIONS: dict[str, str] = {
    "answers_exact_question": "it doesn't answer the exact question that was asked",
    "concrete_situation": "no specific, real situation is described",
    "own_actions": "the candidate's own actions and decisions aren't clear",
    "measurable_result": "no concrete result, such as a number or an observable change",
    "reflection": "no reflection on what was learned",
    "level_fit": "it doesn't show what is expected at this level",
    "correct": "it contains a technical error",
    "depth": "it names the concept without explaining how or why it works",
    "trade_offs": "no trade-offs, limits or alternatives",
    "concrete_example": "no concrete example",
    "consistent_with_reference": "it disagrees with the reference material",
}


def diagnostics_for(record: InterviewRecord, has_passages: bool) -> dict[str, str]:
    """The diagnostic questions for this interview type, in rubric order."""
    if record.interview_type == "hr":
        return dict(HR_DIAGNOSTICS)
    checks = dict(TECH_DIAGNOSTICS)
    if has_passages:
        checks[CONSISTENT_WITH_REFERENCE[0]] = CONSISTENT_WITH_REFERENCE[1]
    return checks


def build_grade_instructions(record: InterviewRecord) -> str:
    """The rubric for the grader's `score` question (contracts/grader.md)."""
    guide = SENIORITY_GUIDE.get(record.seniority, SENIORITY_GUIDE["mid"])
    position = describe_position(record.role, record.seniority)
    return (
        f"Grade the candidate's answer to the question as a strong interviewer would, for {position} "
        f"in a {_kind(record)} interview. Expectations at this level: {guide} "
        "The answer is a transcript of speech: ignore filler words and transcription errors. "
        "Text in [square brackets] is an example detail the candidate will replace with their own; "
        "treat it as a real, specific detail. When reference passages are given, judge the answer "
        "against them. Text inside « » is the role as the candidate wrote it."
    )


# ── Writer: shared header ─────────────────────────────────────────────────────

def build_writer_header(record: InterviewRecord, resume_text: str | None) -> str:
    """What every writer call starts with: the interview, the level, the language, the resume."""
    language_name = LANGUAGE_NAMES.get(record.language, "English")
    level = SENIORITY_LABELS.get(record.seniority, "mid-level")
    guide = SENIORITY_GUIDE.get(record.seniority, SENIORITY_GUIDE["mid"])
    parts = [
        f"Interview type: {_kind(record)}.",
        f"Position: {describe_position(record.role, record.seniority)} "
        "(text inside « » is the role as the candidate wrote it).",
        f"Judge and write for a strong {level} candidate for this role. Expectations at this level: "
        f"{guide} A junior answer is not penalised for missing senior-only depth; a senior answer is "
        "expected to show it.",
        f"Write every piece of feedback, every model answer and the overall section in {language_name}. "
        "Quoted words stay as the candidate spoke them.",
        "Answers are transcripts of speech: ignore filler words and transcription errors.",
    ]
    if resume_text:
        parts.append("Candidate's resume:\n<<<\n" + resume_text.strip() + "\n>>>")
    return "\n\n".join(parts)


def _grade_line(grade: GradeSummary | None) -> str:
    if grade is None:
        levels = "\n".join(f"- {level}" for level in GRADE_LEVELS)
        return "Grade the answer yourself on this scale (put the level in `rating`):\n" + levels
    gaps = "; ".join(grade.gaps) if grade.gaps else "none"
    line = f"Grade: {grade.score:.1f}/5 (level {grade.level}). Gaps found by the grader: {gaps}."
    if grade.level == 5:
        line += (" This answer already earns the top grade: in `missing`, say so, and in `model_answer`, "
                 "tighten the candidate's own answer, keeping their facts and wording.")
    return line


def _question_block(record: InterviewRecord, question: dict, passages: Sequence[str]) -> str:
    block = [f"Question {question['index']}: {question['text']}"]
    spoken = (question.get("spoken_text") or "").strip()
    if spoken and spoken != question["text"]:
        block.append(f"(As the interviewer said it: {spoken})")
    if question.get("is_follow_up"):
        previous = next((q for q in record.questions if q["index"] == question["index"] - 1), None)
        if previous:
            block.append(
                f"(This is a follow-up to the previous question, «{previous['text']}», "
                f"which the candidate answered: «{_answer(previous)}»)"
            )
    if passages:
        block.append("Reference passages for this question:\n" + "\n---\n".join(p.strip() for p in passages))
    block.append(f"Candidate's answer: {_answer(question)}")
    return "\n".join(block)


# ── Writer: per-question feedback and the 5/5 answer ──────────────────────────

# The rules for a 5/5 answer, shared by the first draft and the rewrite.
MODEL_ANSWER_RULES = """\
   - Answer the exact question in the first sentence.
   - First person, spoken style, no lists, headings or labels. 150–230 words.
   - HR (behavioral): one specific situation (the context and what was at stake), the candidate's own \
actions and decisions with the reasoning and trade-offs behind them, a concrete result with a number, \
and one closing sentence on what they learned. Don't name the STAR method.
   - Technical: a correct, direct answer, how it works, one concrete example from the candidate's \
experience, the trade-offs, and when the choice would change. Agree with any reference passages.
   - Pitch it at the level expectations: no senior-only leadership for a junior; ownership, \
trade-offs and impact for a senior.
   - Build on the candidate's own facts first (their answer, then their resume). Every detail they \
didn't give is a short, concrete example value in [square brackets] for them to replace, such as \
[40%], [three weeks] or [Checkout]. Never a description in brackets, and never an unbracketed \
invented fact.
   - If the answer already earns the top grade, tighten the candidate's own answer, keeping their \
facts and wording, instead of writing a different answer.
   - A follow-up question is answered in the context of the previous answer.
   - If the answer contains a factual error, the model answer corrects it."""

MODEL_ANSWER_INSTRUCTIONS = """\
You write the feedback on one answer from a mock job interview, for the candidate, who is practising.

1. The grade is final. Never contradict it, and never mention a different number.
2. `what_worked`: one sentence, quoting the candidate's words when it helps. If the answer didn't \
address the question at all, say so plainly.
3. `missing`: at most two sentences, naming the grader's gaps in plain language, and any factual \
error. If the answer already earns the top grade, say so.
4. `model_answer`: the exact words the candidate should say to get 5/5 on this question.
""" + MODEL_ANSWER_RULES


def question_schema(with_rating: bool) -> dict:
    """The per-question writer's output. `rating` only when the writer grades (fallback)."""
    properties: dict = {
        "what_worked": {"type": "string"},
        "missing": {"type": "string"},
        "model_answer": {"type": "string"},
    }
    required = ["what_worked", "missing", "model_answer"]
    if with_rating:
        properties["rating"] = {"type": "integer", "minimum": 0, "maximum": 5}
        required.append("rating")
    return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


def build_question_input(
    record: InterviewRecord,
    question: dict,
    resume_text: str | None,
    passages: Sequence[str],
    grade: GradeSummary | None,
) -> str:
    """One question as the per-question writer reads it. `grade=None` means the writer grades."""
    return "\n\n".join([
        build_writer_header(record, resume_text),
        _question_block(record, question, passages),
        _grade_line(grade),
    ])


# ── Writer: overall section ───────────────────────────────────────────────────

OVERALL_INSTRUCTIONS = """\
You write the overall section of the feedback on a mock job interview, for the candidate, who is \
practising. Write a summary of two or three sentences that is consistent with the grades, two to four \
strengths, and two to four areas to improve. Each area to improve is concrete: say what to do \
differently, and list in `questions` the question numbers where it showed. The grades are final: \
never contradict them."""

OVERALL_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "strengths", "areas_to_improve"],
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "areas_to_improve": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "questions"],
                "properties": {
                    "text": {"type": "string"},
                    "questions": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
    },
}


def build_overall_input(
    record: InterviewRecord,
    resume_text: str | None,
    grades: dict[int, GradeSummary] | None,
) -> str:
    """Every question, answer and grade. Without grades, the writer judges them itself."""
    parts = [build_writer_header(record, resume_text)]
    for q in record.questions:
        block = f"Question {q['index']}: {q['text']}\nCandidate's answer: {_answer(q)}"
        grade = (grades or {}).get(q["index"])
        if grade is not None:
            gaps = "; ".join(grade.gaps) if grade.gaps else "none"
            block += f"\nGrade: {grade.score:.1f}/5 (level {grade.level}). Gaps: {gaps}."
        parts.append(block)
    if grades is None:
        parts.append("Judge each answer yourself on this scale:\n" + "\n".join(f"- {g}" for g in GRADE_LEVELS))
    return "\n\n".join(parts)


# ── Writer: rewriting a model answer that didn't reach 5 ─────────────────────

REWRITE_INSTRUCTIONS = """\
You rewrite a model answer from the feedback on a mock job interview so that it earns 5/5 with the \
grader, fixing the gaps it named. Return only `model_answer`, the exact words the candidate should say:
""" + MODEL_ANSWER_RULES

REWRITE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model_answer"],
    "properties": {"model_answer": {"type": "string"}},
}


def build_rewrite_input(
    record: InterviewRecord,
    question: dict,
    resume_text: str | None,
    passages: Sequence[str],
    grade: GradeSummary,
    model_answer: str,
    check: GradeSummary,
) -> str:
    gaps = "; ".join(check.gaps) if check.gaps else "none named"
    return "\n\n".join([
        build_question_input(record, question, resume_text, passages, grade),
        "Your previous model answer:\n<<<\n" + model_answer.strip() + "\n>>>",
        f"The grader gave this model answer {check.score:.1f}/5 (level {check.level}). Gaps: {gaps}.",
    ])
