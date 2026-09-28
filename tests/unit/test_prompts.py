"""Unit tests for src/interview/prompts.py (obligations in contracts/agents.md)."""
import pytest

from src.interview.prompts import (
    COMMENTARY_TEMPLATE,
    CONCLUDE_INSTRUCTION,
    GREETING_INSTRUCTION,
    INACTIVITY_INSTRUCTION,
    build_interviewer_instructions,
    build_question_writer_prompt,
)


def instructions(interview_type="technical", language="en", has_resume=False, has_references=False) -> str:
    return build_interviewer_instructions(interview_type, language, has_resume, has_references)


class TestInterviewerInstructions:
    def test_type_and_language(self):
        assert "technical" in instructions("technical")
        assert "HR (behavioral)" in instructions("hr")
        assert "Speak only English" in instructions(language="en")
        assert "Speak only Brazilian Portuguese" in instructions(language="pt-BR")

    def test_never_asks_the_type(self):
        text = instructions()
        assert "Never ask which kind of interview" in text
        assert "HR or technical?" not in text

    def test_delegates_only_for_questions(self):
        text = instructions()
        assert "never write interview questions yourself" in text
        assert "delegate" in text.lower()
        assert "word for word" in text

    def test_never_evaluates(self):
        assert "Never evaluate" in instructions()

    def test_introduction_and_readiness(self):
        text = instructions()
        assert "introduce yourself" in text
        assert "ready" in text
        assert "not yet" in text

    @pytest.mark.parametrize("has_resume,has_references,line", [
        (True, True, "Material: resume and reference material"),
        (True, False, "Material: resume"),
        (False, True, "Material: reference material"),
        (False, False, "Material: none"),
    ])
    def test_material_line(self, has_resume, has_references, line):
        text = instructions(has_resume=has_resume, has_references=has_references)
        assert line + "\n" in text + "\n"
        assert "only if the Material line" in text

    def test_pauses_clarifications_and_ending(self):
        text = instructions()
        assert "let me think" in text
        assert "once" in text                       # V8: one check-in per silence
        assert "repeat or clarify" in text          # V9
        assert "asks to end the interview" in text  # V10


def test_runtime_instructions():
    assert all(w in GREETING_INSTRUCTION for w in ("introduce yourself", "ready", "pause"))
    assert "goodbye" in CONCLUDE_INSTRUCTION and "Ask nothing else" in CONCLUDE_INSTRUCTION
    assert "silent" in INACTIVITY_INSTRUCTION and "goodbye" in INACTIVITY_INSTRUCTION


def test_commentary_template():
    text = COMMENTARY_TEMPLATE.format(question="Q?")
    assert "word for word" in text and "«Q?»" in text


class TestQuestionWriterPrompt:
    def prompt(self, interview_type="technical", language="en", **kw) -> str:
        return build_question_writer_prompt(interview_type, language, **kw)

    def test_rules(self):
        text = self.prompt()
        assert "Output only the question" in text
        assert "at most two short sentences" in text
        assert "Never evaluate" in text
        assert "Never repeat" in text

    def test_language(self):
        assert "Write the question in Brazilian Portuguese" in self.prompt(language="pt-BR")
        assert "even if the resume or reference material" in self.prompt(language="en")

    def test_follow_ups_only_for_technical(self):
        assert "FOLLOW-UP:" in self.prompt("technical")
        assert "FOLLOW-UP:" not in self.prompt("hr")
        assert "Never ask a follow-up" in self.prompt("hr")

    def test_last_exchange_only_for_technical(self):
        exchange = {"question": "What is a mutex?", "answer": "It locks a resource"}
        assert "It locks a resource" in self.prompt("technical", last_exchange=exchange)
        assert "It locks a resource" not in self.prompt("hr", last_exchange=exchange)

    def test_resume_and_fallback(self):
        assert "Five years at Acme" in self.prompt("hr", resume_text="Five years at Acme")
        assert "general software-engineering" in self.prompt("technical")
        assert "general HR" in self.prompt("hr")

    def test_passages_only_technical(self):
        passages = ["Consistent hashing maps keys onto a ring."]
        assert "Consistent hashing" in self.prompt("technical", reference_context=passages)
        assert "Consistent hashing" not in self.prompt("hr", reference_context=passages)

    def test_already_asked(self):
        text = self.prompt(questions_asked=["What is a mutex?"])
        assert "- What is a mutex?" in text


class TestSeniority:
    def test_interviewer_names_role_and_level(self):
        text = build_interviewer_instructions("technical", "en", False, False, role="Backend Engineer", seniority="senior")
        assert "senior «Backend Engineer» position" in text
        assert "appropriate to a senior candidate" in text  # V11

    def test_interviewer_without_role(self):
        text = build_interviewer_instructions("hr", "en", False, False, role=None, seniority="junior")
        assert "a junior candidate" in text
        assert "«" not in text

    def test_question_writer_uses_the_level_guide(self):
        from src.interview.prompts import SENIORITY_GUIDE
        text = build_question_writer_prompt("technical", "en", role="Backend Engineer", seniority="junior")
        assert SENIORITY_GUIDE["junior"] in text
        assert SENIORITY_GUIDE["senior"] not in text
        assert "«Backend Engineer»" in text

    def test_question_writer_without_role(self):
        text = build_question_writer_prompt("hr", "en", seniority="senior")
        assert "a senior candidate" in text

    def test_writer_uses_the_level_guide(self):
        from src.evaluation.prompts import build_question_input
        from src.interview.prompts import SENIORITY_GUIDE
        from src.interview.record import InterviewRecord
        record = InterviewRecord(interview_id="20260925-143210-hr-k3x9qa", interview_type="hr", language="en",
                                 started_at="2026-09-25T14:32:10-03:00", role="Product Manager", seniority="senior")
        text = build_question_input(record, {"index": 1, "text": "Q?", "answer_text": "A."}, None, [], None)
        assert SENIORITY_GUIDE["senior"] in text
        assert "«Product Manager»" in text
        assert "not penalised" in text


def test_interviewer_is_told_to_speak_slowly():
    from src.interview.prompts import SPEAKING_PACE
    for language in ("en", "pt-BR"):
        text = build_interviewer_instructions("hr", language, False, False)
        assert SPEAKING_PACE in text
        assert "slow, unhurried pace" in text


# ── Feedback writer and grader (specs/004) ────────────────────────────────────

class TestFeedbackPrompts:
    @staticmethod
    def record(interview_type="hr", language="pt-BR", seniority="mid"):
        from src.interview.record import InterviewRecord
        rec = InterviewRecord(interview_id="20260926-124939-hr-1buota", interview_type=interview_type,
                              language=language, started_at="2026-09-26T12:49:39+00:00", seniority=seniority)
        rec.questions = [
            {"index": 1, "text": "Como você prioriza?", "spoken_text": "", "is_follow_up": False,
             "answer_text": "Eu alinho com meu gestor."},
            {"index": 2, "text": "E quando o gestor não está?", "spoken_text": "", "is_follow_up": True,
             "answer_text": ""},
        ]
        return rec

    def test_model_answer_rules(self):
        from src.evaluation.prompts import MODEL_ANSWER_INSTRUCTIONS, REWRITE_INSTRUCTIONS
        for text in (MODEL_ANSWER_INSTRUCTIONS, REWRITE_INSTRUCTIONS):
            assert "[40%]" in text and "square brackets" in text
            assert "150–230 words" in text
            assert "Answer the exact question in the first sentence" in text
            assert "tighten the candidate's own answer" in text
        assert "Never contradict it" in MODEL_ANSWER_INSTRUCTIONS

    def test_question_input_with_a_grade(self):
        from src.evaluation.prompts import GradeSummary, build_question_input
        from src.interview.prompts import SENIORITY_GUIDE
        rec = self.record()
        text = build_question_input(rec, rec.questions[0], None, [], GradeSummary(1.31, 1, ["no concrete result"]))
        assert "Grade: 1.3/5 (level 1)" in text
        assert "no concrete result" in text
        assert SENIORITY_GUIDE["mid"] in text
        assert "Brazilian Portuguese" in text
        assert "Eu alinho com meu gestor." in text
        assert "tighten" not in text

    def test_level_5_gets_the_tighten_rule(self):
        from src.evaluation.prompts import GradeSummary, build_question_input
        rec = self.record()
        text = build_question_input(rec, rec.questions[0], None, [], GradeSummary(4.8, 5, []))
        assert "already earns the top grade" in text and "tighten" in text

    def test_question_input_without_a_grade_lists_the_levels(self):
        from src.evaluation.prompts import GRADE_LEVELS, build_question_input
        rec = self.record()
        text = build_question_input(rec, rec.questions[0], None, [], None)
        assert "Grade the answer yourself" in text
        assert all(level in text for level in GRADE_LEVELS)

    def test_follow_up_and_passages(self):
        from src.evaluation.prompts import build_question_input
        rec = self.record("technical")
        text = build_question_input(rec, rec.questions[1], None, ["Queues decouple producers."], None)
        assert "follow-up to the previous question" in text and "Como você prioriza?" in text
        assert "Queues decouple producers." in text
        assert "Candidate's answer: (no answer)" in text

    def test_question_schema(self):
        from src.evaluation.prompts import question_schema
        with_rating = question_schema(True)
        assert "rating" in with_rating["required"]
        assert with_rating["properties"]["rating"] == {"type": "integer", "minimum": 0, "maximum": 5}
        assert "rating" not in question_schema(False)["properties"]

    def test_grade_rubric(self):
        from src.evaluation.prompts import build_grade_instructions, diagnostics_for
        from src.interview.prompts import SENIORITY_GUIDE
        rec = self.record(seniority="junior")
        text = build_grade_instructions(rec)
        assert SENIORITY_GUIDE["junior"] in text
        assert "square brackets" in text and "transcript of speech" in text
        assert list(diagnostics_for(rec, False)) == [
            "answers_exact_question", "concrete_situation", "own_actions", "measurable_result", "reflection", "level_fit"]
        tech = self.record("technical")
        assert list(diagnostics_for(tech, False)) == [
            "answers_exact_question", "correct", "depth", "trade_offs", "concrete_example", "level_fit"]
        assert list(diagnostics_for(tech, True))[-1] == "consistent_with_reference"

    def test_every_diagnostic_has_a_gap_description(self):
        from src.evaluation.prompts import CONSISTENT_WITH_REFERENCE, GAP_DESCRIPTIONS, HR_DIAGNOSTICS, TECH_DIAGNOSTICS
        ids = {*HR_DIAGNOSTICS, *TECH_DIAGNOSTICS, CONSISTENT_WITH_REFERENCE[0]}
        assert ids <= set(GAP_DESCRIPTIONS)
