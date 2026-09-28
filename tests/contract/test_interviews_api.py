"""Contract tests for the interview files API (specs/002-gpt-live-interview/contracts/http-api.md)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.evaluation.report import save_report
from src.interview.record import InterviewRecord, save_record

ID = "20260925-143210-hr-k3x9qa"


@pytest.fixture
def client():
    from src.app import app
    return TestClient(app)


@pytest.fixture
def record(tmp_interviews_dir) -> InterviewRecord:
    rec = InterviewRecord(interview_id=ID, interview_type="hr", language="pt-BR", started_at="2026-09-25T14:32:10-03:00")
    rec.questions.append({"index": 1, "text": "Fale de um projeto.", "spoken_text": "", "is_follow_up": False,
                          "answer_text": "Liderei a migração.", "answered_at": None})
    save_record(rec)
    return rec


def with_report(rec: InterviewRecord) -> None:
    save_report(rec, {
        "grader": "jev", "grader_model": "typesafe/jev-1.13-20260917", "writer_model": "gpt-6-sol",
        "per_question": [{"index": 1, "score": 3.64, "level": 4, "what_worked": "Claro.",
                          "missing": "Faltou um número no resultado.",
                          "model_answer": "Liderei a migração de [Checkout] e reduzi os erros em [40%].",
                          "model_answer_check": {"passed": True, "score": 4.7, "level": 5, "rewritten": False}}],
        "overall": {"summary": "Bom.", "strengths": ["Clareza"],
                    "areas_to_improve": [{"text": "Métricas", "questions": [1]}]},
    })
    rec.report_status = "ready"
    save_record(rec)


def with_v1_report(rec: InterviewRecord) -> dict:
    """A report written before 004 (format 1): it must be served exactly as it is on disk."""
    import json
    v1 = {
        "interview_id": rec.interview_id, "generated_at": "2026-09-25T15:00:00-03:00", "model": "gpt-6-sol",
        "language": "pt-BR", "interview_type": "hr", "role": None, "seniority": "mid",
        "questions": [{"index": 1, "text": "Fale de um projeto.", "answer_text": "Liderei a migração."}],
        "per_question": [{"index": 1, "rating": 4, "what_worked": "Claro.", "to_improve": "Mais números."}],
        "overall": {"summary": "Bom.", "strengths": ["Clareza"], "areas_to_improve": ["Métricas"]},
    }
    (rec.folder / "report.json").write_text(json.dumps(v1, ensure_ascii=False), encoding="utf-8")
    (rec.folder / "report.md").write_text("# Feedback da entrevista\n\n**O que melhorar:** Mais números.\n",
                                          encoding="utf-8")
    rec.report_status = "ready"
    save_record(rec)
    return v1


def test_summary(client, record):
    body = client.get(f"/api/interviews/{ID}").json()
    assert body == {
        "interview_id": ID, "interview_type": "hr", "language": "pt-BR",
        "started_at": "2026-09-25T14:32:10-03:00", "ended_at": None, "end_reason": None,
        "question_count": 1, "report_status": "none",
        "role": None, "seniority": "mid",
    }


def test_transcript_download(client, record):
    res = client.get(f"/api/interviews/{ID}/transcript")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f'filename="interview-{ID}.md"' in res.headers["content-disposition"]
    assert "Liderei a migração." in res.text


def test_report_not_ready(client, record):
    res = client.get(f"/api/interviews/{ID}/report")
    assert res.status_code == 404
    assert res.json()["code"] == "REPORT_NOT_READY"


def test_report_download_and_json(client, record):
    with_report(record)
    res = client.get(f"/api/interviews/{ID}/report")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f'filename="interview-{ID}-report.md"' in res.headers["content-disposition"]
    assert "O que funcionou" in res.text
    assert "Resposta 5/5" in res.text and "Nota: 3,6/5" in res.text
    body = client.get(f"/api/interviews/{ID}/report?format=json").json()
    assert body["format"] == 2
    assert body["grader"] == "jev"
    assert body["per_question"][0]["score"] == 3.64   # as the grader returned it
    assert body["per_question"][0]["model_answer"].startswith("Liderei a migração de [Checkout]")
    assert body["questions"] == [{"index": 1, "text": "Fale de um projeto.", "answer_text": "Liderei a migração."}]
    assert client.get(f"/api/interviews/{ID}").json()["report_status"] == "ready"


def test_format_1_report_is_served_unchanged(client, record):
    v1 = with_v1_report(record)
    body = client.get(f"/api/interviews/{ID}/report?format=json").json()
    assert body == v1 and "format" not in body
    res = client.get(f"/api/interviews/{ID}/report")
    assert res.status_code == 200
    assert f'filename="interview-{ID}-report.md"' in res.headers["content-disposition"]
    assert "O que melhorar" in res.text


@pytest.mark.parametrize("bad_id", [
    "20260925-143210-hr-zzzzzz",   # well-formed but missing
    "not-an-id",
    "..%2F..%2Fetc",
    "20260925-143210-sales-k3x9qa",
])
def test_not_found(client, record, bad_id):
    for path in ("", "/transcript", "/report"):
        res = client.get(f"/api/interviews/{bad_id}{path}")
        assert res.status_code == 404
        # An encoded path separator is refused by the router itself, before our handler.
        assert res.json().get("code", "INTERVIEW_NOT_FOUND") == "INTERVIEW_NOT_FOUND"


def test_summary_carries_role_and_seniority(client, tmp_interviews_dir):
    rec = InterviewRecord(interview_id=ID, interview_type="hr", language="en",
                          started_at="2026-09-25T14:32:10-03:00", role="Backend Engineer", seniority="senior")
    save_record(rec)
    body = client.get(f"/api/interviews/{ID}").json()
    assert (body["role"], body["seniority"]) == ("Backend Engineer", "senior")


def test_older_record_without_role_loads(client, tmp_interviews_dir):
    import json
    folder = tmp_interviews_dir / ID
    folder.mkdir(parents=True)
    (folder / "record.json").write_text(json.dumps({
        "interview_id": ID, "interview_type": "hr", "language": "en", "started_at": "2026-09-25T14:32:10-03:00",
        "ended_at": None, "end_reason": None, "report_status": "none", "resume_filename": None,
        "reference_filenames": [], "questions": [],
    }))
    body = client.get(f"/api/interviews/{ID}").json()
    assert (body["role"], body["seniority"]) == (None, "mid")
