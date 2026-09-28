"""
The evaluation report: report.json and report.md (specs/004-exact-answer-feedback/contracts/report.md).

Reports are written in format 2: per question the grader's score (0–5, as returned),
what worked, what was missing and the exact 5/5 answer. Format 1 reports (a 1–5
`rating` and `to_improve`, from before 004) are never rewritten, but still render.

Answers are always quoted from the record, never from a model. Fixed labels follow
the interview language.
"""
from __future__ import annotations

import json

from src.interview.record import InterviewRecord, now_iso, position_line, write_atomic

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Interview feedback", "hr": "HR interview", "technical": "Technical interview",
        "question": "Question", "answer": "Your answer", "rating": "Rating",
        "what_worked": "What worked", "to_improve": "To improve",
        "summary": "Summary", "strengths": "Strengths", "areas_to_improve": "Areas to improve",
        "no_answer": "(no answer)",
        "junior": "Junior", "mid": "Mid-level", "senior": "Senior",
        "score": "Score", "missing": "What was missing", "model_answer": "5/5 answer",
        "model_answer_hint": "replace what's in [brackets] with your own details",
        "check_note": "This version scored {score} with the grader.",
        "fallback_grades": "Grades given by the writer (grader unavailable).",
        "area_questions": "questions",
    },
    "pt-BR": {
        "title": "Feedback da entrevista", "hr": "Entrevista de RH", "technical": "Entrevista técnica",
        "question": "Pergunta", "answer": "Sua resposta", "rating": "Nota",
        "what_worked": "O que funcionou", "to_improve": "O que melhorar",
        "summary": "Resumo", "strengths": "Pontos fortes", "areas_to_improve": "Pontos a melhorar",
        "no_answer": "(sem resposta)",
        "junior": "Júnior", "mid": "Pleno", "senior": "Sênior",
        "score": "Nota", "missing": "O que faltou", "model_answer": "Resposta 5/5",
        "model_answer_hint": "troque o que está entre [colchetes] pelos seus dados",
        "check_note": "Esta versão tirou {score} no avaliador.",
        "fallback_grades": "Notas dadas pelo redator (avaliador indisponível).",
        "area_questions": "perguntas",
    },
}


def format_score(value: float, language: str) -> str:
    """The grader's score with one decimal and the language's separator: 1.3/5, or 1,3/5 in PT-BR."""
    text = f"{value:.1f}"
    return (text.replace(".", ",") if language == "pt-BR" else text) + "/5"


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.strip().splitlines())


def render_report_md(record: InterviewRecord, report: dict) -> str:
    # run_evaluation's output carries `grader`; a saved format 2 report.json also carries `format`.
    if report.get("format") == 2 or "grader" in report:
        return _render_v2(record, report)
    return _render_v1(record, report)


def _render_v2(record: InterviewRecord, report: dict) -> str:
    labels = LABELS.get(record.language, LABELS["en"])
    language = record.language
    feedback = {item["index"]: item for item in report["per_question"]}
    lines = [
        f"# {labels['title']}",
        "",
        f"{labels[record.interview_type]} · {position_line(record, labels)} · {record.started_at[:10]}",
        "",
    ]
    if report.get("grader") == "writer":
        lines += [f"_{labels['fallback_grades']}_", ""]
    for q in record.questions:
        item = feedback.get(q["index"])
        answer = (q.get("answer_text") or "").strip() or labels["no_answer"]
        lines += [f"## {labels['question']} {q['index']}", "", q["text"], "", f"**{labels['answer']}:**", "",
                  _quote(answer), ""]
        if item is None:
            continue
        lines += [
            f"**{labels['score']}: {format_score(item['score'], language)}**",
            "",
            f"**{labels['what_worked']}:** {item['what_worked']}",
            "",
            f"**{labels['missing']}:** {item['missing']}",
            "",
            f"**{labels['model_answer']}** ({labels['model_answer_hint']}):",
            "",
            _quote(item["model_answer"]),
            "",
        ]
        check = item.get("model_answer_check")
        if check and not check["passed"]:
            lines += [f"_{labels['check_note'].format(score=format_score(check['score'], language))}_", ""]
    overall = report["overall"]
    lines += [f"## {labels['summary']}", "", overall["summary"], "", f"### {labels['strengths']}", ""]
    lines += [f"- {s}" for s in overall["strengths"]] + ["", f"### {labels['areas_to_improve']}", ""]
    for area in overall["areas_to_improve"]:
        where = f" ({labels['area_questions']} {', '.join(str(i) for i in area['questions'])})" if area["questions"] else ""
        lines.append(f"- {area['text']}{where}")
    return "\n".join(lines).rstrip() + "\n"


def _render_v1(record: InterviewRecord, report: dict) -> str:
    """Reports from before 004: a 1–5 rating and `to_improve`."""
    labels = LABELS.get(record.language, LABELS["en"])
    feedback = {item["index"]: item for item in report["per_question"]}
    lines = [
        f"# {labels['title']}",
        "",
        f"{labels[record.interview_type]} · {position_line(record, labels)} · {record.started_at[:10]}",
        "",
    ]
    for q in record.questions:
        item = feedback.get(q["index"], {})
        answer = (q.get("answer_text") or "").strip() or labels["no_answer"]
        lines += [
            f"## {labels['question']} {q['index']}",
            "",
            q["text"],
            "",
            f"**{labels['answer']}:**",
            "",
            f"> {answer}",
            "",
            f"**{labels['rating']}: {item.get('rating', '–')}/5**",
            "",
            f"**{labels['what_worked']}:** {item.get('what_worked', '')}",
            "",
            f"**{labels['to_improve']}:** {item.get('to_improve', '')}",
            "",
        ]
    overall = report["overall"]
    lines += [f"## {labels['summary']}", "", overall["summary"], "", f"### {labels['strengths']}", ""]
    lines += [f"- {s}" for s in overall["strengths"]] + ["", f"### {labels['areas_to_improve']}", ""]
    lines += [f"- {a}" for a in overall["areas_to_improve"]]
    return "\n".join(lines).rstrip() + "\n"


def save_report(record: InterviewRecord, report: dict) -> None:
    """Write report.json (format 2) and report.md. `report` is run_evaluation's output."""
    payload = {
        "format": 2,
        "interview_id": record.interview_id,
        "generated_at": now_iso(),
        "grader": report["grader"],
        "grader_model": report.get("grader_model"),
        "writer_model": report["writer_model"],
        "model": report["writer_model"],  # kept for readers of format 1
        "language": record.language,
        "interview_type": record.interview_type,
        "role": record.role,
        "seniority": record.seniority,
        # Questions and answers come from the record, never from the model.
        "questions": [
            {"index": q["index"], "text": q["text"], "answer_text": q.get("answer_text") or ""}
            for q in record.questions
        ],
        "per_question": report["per_question"],
        "overall": report["overall"],
    }
    write_atomic(record.folder / "report.json", json.dumps(payload, indent=2, ensure_ascii=False))
    write_atomic(record.folder / "report.md", render_report_md(record, report))
