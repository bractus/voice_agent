"""Unit tests for transcript.md and report.md rendering."""
from src.evaluation.report import format_score, render_report_md
from src.interview.record import InterviewRecord, render_transcript_md


def record(language="en") -> InterviewRecord:
    rec = InterviewRecord(interview_id="20260925-143210-hr-k3x9qa", interview_type="hr",
                          language=language, started_at="2026-09-25T14:32:10-03:00")
    rec.questions = [
        {"index": 1, "text": "Tell me about a conflict.", "spoken_text": "", "is_follow_up": False,
         "answer_text": "I talked to my teammate.", "answered_at": None},
        {"index": 2, "text": "What motivates you?", "spoken_text": "", "is_follow_up": False,
         "answer_text": "", "answered_at": None},
    ]
    return rec


# Format 1: reports written before specs/004. They still render the old way.
REPORT = {
    "per_question": [
        # The model's copy of the answer must never be used: answers come from the record.
        {"index": 1, "rating": 4, "what_worked": "Clear.", "to_improve": "Add the outcome.",
         "answer_text": "MODEL REWROTE THIS"},
        {"index": 2, "rating": 1, "what_worked": "-", "to_improve": "Answer the question."},
    ],
    "overall": {"summary": "A good start.", "strengths": ["Honesty"], "areas_to_improve": ["Structure", "Examples"]},
}


def test_transcript_lists_questions_and_answers():
    text = render_transcript_md(record())
    assert "**Q1.** Tell me about a conflict." in text
    assert "> I talked to my teammate." in text
    assert "**Q2.** What motivates you?" in text
    assert "> (no answer)" in text


def test_format_1_layout_in_english():
    text = render_report_md(record(), REPORT)
    assert "HR interview · Mid-level · 2026-09-25" in text
    assert "## Question 1" in text and "Tell me about a conflict." in text
    assert "> I talked to my teammate." in text
    assert "MODEL REWROTE THIS" not in text
    assert "**Rating: 4/5**" in text
    assert "**What worked:** Clear." in text and "**To improve:** Add the outcome." in text
    assert "## Summary" in text and "- Honesty" in text and "- Structure" in text


def test_format_1_labels_in_portuguese():
    text = render_report_md(record("pt-BR"), REPORT)
    for label in ("Pergunta 1", "Sua resposta", "O que funcionou", "O que melhorar", "Resumo",
                  "Pontos fortes", "Pontos a melhorar", "Entrevista de RH", "Nota: 4/5"):
        assert label in text


# ── Format 2 (specs/004) ──────────────────────────────────────────────────────

MODEL_ANSWER = "When [three requests] landed in one week, I ranked them by risk and cut the delay by [40%].\nI learned to ask early."

REPORT_V2 = {
    "grader": "jev", "grader_model": "typesafe/jev-1.13-20260917", "writer_model": "gpt-6-sol",
    "per_question": [
        {"index": 1, "score": 1.31, "level": 1, "what_worked": "Clear.", "missing": "No result.",
         "model_answer": MODEL_ANSWER, "answer_text": "MODEL REWROTE THIS",
         "model_answer_check": {"passed": True, "score": 4.7, "level": 5, "rewritten": False}},
        {"index": 2, "score": 0.2, "level": 0, "what_worked": "It didn't answer.", "missing": "Answer it.",
         "model_answer": "What motivates me is [shipping to users].",
         "model_answer_check": {"passed": False, "score": 4.24, "level": 4, "rewritten": True}},
    ],
    "overall": {"summary": "A start.", "strengths": ["Honesty"],
                "areas_to_improve": [{"text": "Give numbers", "questions": [1, 2]}, {"text": "Pace", "questions": []}]},
}


def test_format_score():
    assert format_score(1.31, "en") == "1.3/5"
    assert format_score(1.31, "pt-BR") == "1,3/5"
    assert format_score(5, "en") == "5.0/5"


def test_format_2_layout_in_english():
    text = render_report_md(record(), REPORT_V2)
    assert "> I talked to my teammate." in text and "MODEL REWROTE THIS" not in text
    assert "**Score: 1.3/5**" in text
    assert "**What worked:** Clear." in text and "**What was missing:** No result." in text
    assert "**5/5 answer** (replace what's in [brackets] with your own details):" in text
    assert "> When [three requests] landed in one week" in text and "> I learned to ask early." in text
    assert "This version scored 4.2/5 with the grader." in text
    assert "This version scored 4.7/5" not in text          # a passing answer has no note
    assert "- Give numbers (questions 1, 2)" in text and "- Pace\n" in text + "\n"
    assert "grader unavailable" not in text


def test_format_2_labels_in_portuguese():
    text = render_report_md(record("pt-BR"), REPORT_V2)
    for label in ("**Nota: 1,3/5**", "O que faltou", "**Resposta 5/5** (troque o que está entre [colchetes]",
                  "Esta versão tirou 4,2/5 no avaliador.", "(perguntas 1, 2)", "Pontos a melhorar"):
        assert label in text


def test_fallback_report_says_who_graded():
    fallback = {**REPORT_V2, "grader": "writer", "grader_model": None,
                "per_question": [{**q, "model_answer_check": None} for q in REPORT_V2["per_question"]]}
    text = render_report_md(record("pt-BR"), fallback)
    assert "Notas dadas pelo redator (avaliador indisponível)." in text
    assert "no avaliador." not in text
