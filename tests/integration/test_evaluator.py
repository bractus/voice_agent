"""The evaluation against the real writer (gpt-6-sol) and, when its key is set, the real Jev."""
import pytest

from src import config
from src.evaluation.evaluator import run_evaluation, validate_report
from src.interview.record import InterviewRecord
from tests.integration import requires_openai, requires_openrouter

pytestmark = [pytest.mark.integration, requires_openai]


def record() -> InterviewRecord:
    rec = InterviewRecord(interview_id="20260925-143210-hr-k3x9qa", interview_type="hr",
                          language="en", started_at="2026-09-25T14:32:10-03:00")
    rec.questions = [
        {"index": 1, "text": "Tell me about a time you disagreed with a teammate.", "spoken_text": "",
         "answer_text": "We disagreed about the release date. I set up a call, we compared the risks, "
                        "and we agreed to ship behind a feature flag. It went out on time.", "answered_at": None},
        {"index": 2, "text": "What motivates you?", "spoken_text": "",
         "answer_text": "Um, I guess money.", "answered_at": None},
    ]
    return rec


def assert_spoken_model_answers(report):
    for item in report["per_question"]:
        words = len(item["model_answer"].split())
        assert 100 <= words <= 260, words
        assert "[" in item["model_answer"] or item["level"] == 5


async def test_writer_graded(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    rec = record()
    report = await run_evaluation(rec)
    assert validate_report(report, rec) is report
    assert report["grader"] == "writer"
    scores = {item["index"]: item["score"] for item in report["per_question"]}
    assert scores[1] > scores[2]
    assert_spoken_model_answers(report)


@requires_openrouter
async def test_jev_graded_and_checked():
    rec = record()
    report = await run_evaluation(rec)
    assert report["grader"] == "jev" and report["grader_model"].startswith("typesafe/jev")
    scores = {item["index"]: item["score"] for item in report["per_question"]}
    assert scores[1] > scores[2]
    assert all(item["model_answer_check"] is not None for item in report["per_question"])
    assert_spoken_model_answers(report)
