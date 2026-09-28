"""
The evaluation flow (src/evaluation/evaluator.py, specs/004 data-model.md "Evaluation flow").

The writer is faked at `evaluator._call_writer` and the grader at `evaluator.grade_answer`,
so nothing reaches the network.
"""
from __future__ import annotations

import asyncio

import pytest

from src import config
from src.evaluation import evaluator
from src.evaluation.evaluator import EvaluationFailedError, run_evaluation
from src.evaluation.grader import GraderResult, GraderUnavailableError
from src.interview.record import InterviewRecord

MODEL_ANSWER = "Na [Vobys], quando [três demandas] chegaram juntas, comparei impacto e prazo e reduzi o atraso em [40%]."
REWRITTEN = "Na [Vobys], priorizei por risco e prazo, negociei um adiamento e entreguei em [duas semanas]."


def record(n=2, interview_type="hr") -> InterviewRecord:
    rec = InterviewRecord(interview_id="20260926-124939-hr-1buota", interview_type=interview_type,
                          language="pt-BR", started_at="2026-09-26T12:49:39+00:00")
    rec.questions = [{"index": i, "text": f"Pergunta {i}?", "spoken_text": "", "is_follow_up": False,
                      "answer_text": f"Resposta {i}."} for i in range(1, n + 1)]
    return rec


def graded(score: float, level: int, gaps=()) -> GraderResult:
    probabilities = {k: (0.9 if k == level else 0.02) for k in range(6)}
    return GraderResult(score, level, probabilities, 0.8, list(gaps), "typesafe/jev-1.13-20260917")


class FakeWriter:
    """Records every writer call and answers by call name."""

    def __init__(self, monkeypatch, rating=3, fail_names=(), rewrite=REWRITTEN) -> None:
        self.calls: list[dict] = []
        self.rating = rating
        self.fail_names = set(fail_names)
        self.rewrite = rewrite
        self.in_flight = 0
        self.max_in_flight = 0
        monkeypatch.setattr(evaluator, "_call_writer", self)

    async def __call__(self, name, instructions, input_text, schema):
        self.calls.append({"name": name, "input": input_text, "schema": schema})
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        if name in self.fail_names:
            raise RuntimeError("writer down")
        if name == "overall":
            return {"summary": "Resumo.", "strengths": ["Clareza"],
                    "areas_to_improve": [{"text": "Dê números.", "questions": [1, 99]}]}
        if name == "model_answer_rewrite":
            return {"model_answer": self.rewrite}
        data = {"what_worked": "Foi direto.", "missing": "Faltou um resultado.", "model_answer": MODEL_ANSWER}
        if "rating" in schema["properties"]:
            data["rating"] = self.rating
        return data

    def of(self, name):
        return [c for c in self.calls if c["name"] == name]


class FakeGrader:
    """Scripted grades: candidate answers by index, then model answers by text."""

    def __init__(self, monkeypatch, candidates, model_answers=None, fail=None) -> None:
        self.candidates = candidates
        self.model_answers = model_answers or {}
        self.fail = fail or (lambda answer_text: False)
        self.calls: list[str] = []
        monkeypatch.setattr(evaluator, "grade_answer", self)

    async def __call__(self, record, question, answer_text, passages=()):
        self.calls.append(answer_text)
        if self.fail(answer_text):
            raise GraderUnavailableError("down")
        if answer_text in self.model_answers:
            return self.model_answers[answer_text]
        return self.candidates[question["index"]]


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")


# ── Writer-graded path (US1, and the fallback) ───────────────────────────────

async def test_writer_grades_without_a_key(monkeypatch, no_key):
    writer = FakeWriter(monkeypatch, rating=2)
    report = await run_evaluation(record())
    assert report["grader"] == "writer" and report["grader_model"] is None
    assert len(writer.of("question_feedback")) == 2 and len(writer.of("overall")) == 1
    assert all("rating" in c["schema"]["properties"] for c in writer.of("question_feedback"))
    entry = report["per_question"][0]
    assert entry["score"] == 2.0 and entry["level"] == 2
    assert entry["model_answer"] == MODEL_ANSWER and entry["model_answer_check"] is None


async def test_writer_calls_run_in_parallel(monkeypatch, no_key):
    writer = FakeWriter(monkeypatch)
    await run_evaluation(record(4))
    assert writer.max_in_flight == 5   # 4 questions + the overall call


async def test_unknown_area_indexes_are_dropped(monkeypatch, no_key):
    FakeWriter(monkeypatch)
    report = await run_evaluation(record())
    assert report["overall"]["areas_to_improve"] == [{"text": "Dê números.", "questions": [1]}]


async def test_a_failing_writer_call_fails_the_evaluation(monkeypatch, no_key):
    writer = FakeWriter(monkeypatch, fail_names={"question_feedback"})
    with pytest.raises(EvaluationFailedError):
        await run_evaluation(record(1))
    assert len(writer.of("question_feedback")) == 2   # one retry


async def test_an_invalid_output_is_retried_once(monkeypatch, no_key):
    writer = FakeWriter(monkeypatch)
    outputs = [{"what_worked": "x", "missing": "y", "model_answer": "- a list", "rating": 3}]
    real = writer.__call__

    async def flaky(name, instructions, input_text, schema):
        if name == "question_feedback" and outputs:
            writer.calls.append({"name": name, "input": input_text, "schema": schema})
            return outputs.pop()
        return await real(name, instructions, input_text, schema)

    monkeypatch.setattr(evaluator, "_call_writer", flaky)
    report = await run_evaluation(record(1))
    assert report["per_question"][0]["model_answer"] == MODEL_ANSWER


# ── Jev path (US2) ────────────────────────────────────────────────────────────

async def test_grades_come_from_the_grader(monkeypatch, with_key):
    writer = FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(1.31, 1, ["measurable_result"]), 2: graded(3.72, 4)},
               {MODEL_ANSWER: graded(4.7, 5)})
    report = await run_evaluation(record())
    assert report["grader"] == "jev" and report["grader_model"] == "typesafe/jev-1.13-20260917"
    assert [(e["score"], e["level"]) for e in report["per_question"]] == [(1.31, 1), (3.72, 4)]
    feedback_calls = writer.of("question_feedback")
    assert all("rating" not in c["schema"]["properties"] for c in feedback_calls)
    assert "Grade: 1.3/5 (level 1)" in feedback_calls[0]["input"]
    assert "no concrete result" in feedback_calls[0]["input"]
    assert "Grade: 1.3/5" in writer.of("overall")[0]["input"]


async def test_a_passing_model_answer_is_not_rewritten(monkeypatch, with_key):
    writer = FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(1.3, 1)}, {MODEL_ANSWER: graded(4.7, 5)})
    report = await run_evaluation(record(1))
    assert report["per_question"][0]["model_answer_check"] == {"passed": True, "score": 4.7, "level": 5, "rewritten": False}
    assert writer.of("model_answer_rewrite") == []


async def test_a_failing_model_answer_is_rewritten_once(monkeypatch, with_key):
    writer = FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(1.3, 1)},
               {MODEL_ANSWER: graded(3.9, 4, ["reflection"]), REWRITTEN: graded(4.6, 5)})
    report = await run_evaluation(record(1))
    entry = report["per_question"][0]
    assert entry["model_answer"] == REWRITTEN
    assert entry["model_answer_check"] == {"passed": True, "score": 4.6, "level": 5, "rewritten": True}
    rewrite = writer.of("model_answer_rewrite")
    assert len(rewrite) == 1
    assert "3.9/5 (level 4)" in rewrite[0]["input"] and MODEL_ANSWER in rewrite[0]["input"]


async def test_a_still_failing_rewrite_keeps_the_higher_score(monkeypatch, with_key):
    FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(1.3, 1)}, {MODEL_ANSWER: graded(4.1, 4), REWRITTEN: graded(3.8, 4)})
    entry = (await run_evaluation(record(1)))["per_question"][0]
    assert entry["model_answer"] == MODEL_ANSWER
    assert entry["model_answer_check"] == {"passed": False, "score": 4.1, "level": 4, "rewritten": False}

    FakeGrader(monkeypatch, {1: graded(1.3, 1)}, {MODEL_ANSWER: graded(3.8, 4), REWRITTEN: graded(4.2, 4)})
    entry = (await run_evaluation(record(1)))["per_question"][0]
    assert entry["model_answer"] == REWRITTEN
    assert entry["model_answer_check"] == {"passed": False, "score": 4.2, "level": 4, "rewritten": True}


async def test_a_top_answer_gets_the_tighten_path(monkeypatch, with_key):
    writer = FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(4.8, 5)}, {MODEL_ANSWER: graded(4.8, 5)})
    await run_evaluation(record(1))
    assert "already earns the top grade" in writer.of("question_feedback")[0]["input"]


async def test_a_dead_grader_falls_back_for_the_whole_report(monkeypatch, with_key):
    writer = FakeWriter(monkeypatch, rating=3)
    grader = FakeGrader(monkeypatch, {1: graded(1.3, 1), 2: graded(2.0, 2)},
                        fail=lambda answer: answer == "Resposta 2.")
    report = await run_evaluation(record())
    assert report["grader"] == "writer" and report["grader_model"] is None
    assert [e["score"] for e in report["per_question"]] == [3.0, 3.0]
    assert all(e["model_answer_check"] is None for e in report["per_question"])
    assert all("rating" in c["schema"]["properties"] for c in writer.of("question_feedback"))
    assert len(grader.calls) == 2   # no checks in fallback


async def test_a_failed_check_leaves_that_entry_unchecked(monkeypatch, with_key):
    FakeWriter(monkeypatch)
    FakeGrader(monkeypatch, {1: graded(1.3, 1)}, fail=lambda answer: answer == MODEL_ANSWER)
    report = await run_evaluation(record(1))
    assert report["grader"] == "jev"
    assert report["per_question"][0]["model_answer_check"] is None


async def test_a_failed_rewrite_keeps_the_first_version(monkeypatch, with_key):
    FakeWriter(monkeypatch, fail_names={"model_answer_rewrite"})
    FakeGrader(monkeypatch, {1: graded(1.3, 1)}, {MODEL_ANSWER: graded(3.9, 4)})
    entry = (await run_evaluation(record(1)))["per_question"][0]
    assert entry["model_answer"] == MODEL_ANSWER
    assert entry["model_answer_check"]["passed"] is False
