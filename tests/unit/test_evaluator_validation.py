"""Unit tests for the format 2 report validation (src/evaluation/evaluator.py, data-model.md)."""
import copy

import pytest

from src.evaluation.evaluator import InvalidReportError, validate_report
from src.interview.record import InterviewRecord

MODEL_ANSWER = "Na [Vobys], quando [três demandas] chegaram juntas, eu comparei impacto e prazo e reduzi o atraso em [40%]."


def record(n=2) -> InterviewRecord:
    rec = InterviewRecord(interview_id="20260925-143210-hr-k3x9qa", interview_type="hr",
                          language="en", started_at="2026-09-25T14:32:10-03:00")
    rec.questions = [{"index": i, "text": f"Q{i}", "answer_text": f"A{i}"} for i in range(1, n + 1)]
    return rec


def report(indexes=(1, 2), **entry) -> dict:
    item = {"score": 3.4, "level": 3, "what_worked": "x", "missing": "y", "model_answer": MODEL_ANSWER,
            "model_answer_check": {"passed": True, "score": 4.7, "level": 5, "rewritten": False}}
    item.update(entry)
    return {
        "grader": "jev", "grader_model": "typesafe/jev-1.13", "writer_model": "gpt-6-sol",
        "per_question": [{"index": i, **copy.deepcopy(item)} for i in indexes],
        "overall": {"summary": "s", "strengths": ["a"], "areas_to_improve": [{"text": "b", "questions": [1]}]},
    }


def test_valid():
    assert validate_report(report(), record()) == report()


def test_fallback_entry_without_a_check_is_valid():
    assert validate_report(report(model_answer_check=None, score=3.0), record())


@pytest.mark.parametrize("indexes", [(1,), (1, 2, 3), (1, 1)])
def test_index_set_must_match(indexes):
    with pytest.raises(InvalidReportError):
        validate_report(report(indexes), record())


@pytest.mark.parametrize("score", [5.01, -0.1, "4", True, None])
def test_score_range(score):
    with pytest.raises(InvalidReportError):
        validate_report(report(score=score), record())


@pytest.mark.parametrize("level", [6, -1, 2.5, True])
def test_level_range(level):
    with pytest.raises(InvalidReportError):
        validate_report(report(level=level), record())


def test_scores_keep_their_decimals():
    assert validate_report(report(score=1.31), record())["per_question"][0]["score"] == 1.31


def test_model_answer_word_cap():
    validate_report(report(model_answer=" ".join(["palavra"] * 260)), record())
    with pytest.raises(InvalidReportError):
        validate_report(report(model_answer=" ".join(["palavra"] * 261)), record())


@pytest.mark.parametrize("text", ["Intro\n- first point", "## Heading\ntext", "1. first\n2. second", "* item", ""])
def test_model_answer_is_spoken_prose(text):
    with pytest.raises(InvalidReportError):
        validate_report(report(model_answer=text), record())


@pytest.mark.parametrize("check", [{"passed": "yes", "score": 4.0, "level": 4, "rewritten": False},
                                   {"passed": True, "score": 7, "level": 5, "rewritten": False},
                                   {"passed": True, "score": 4.0, "level": 5}])
def test_malformed_check(check):
    with pytest.raises(InvalidReportError):
        validate_report(report(model_answer_check=check), record())


def test_areas_must_name_their_questions():
    bad = report()
    bad["overall"]["areas_to_improve"] = ["Depth"]
    with pytest.raises(InvalidReportError):
        validate_report(bad, record())


def test_malformed():
    with pytest.raises(InvalidReportError):
        validate_report({"per_question": []}, record())
