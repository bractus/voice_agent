"""Unit tests for building the question writer's request (src/interview/questions.py)."""
from src.config import RESUME_PROMPT_MAX_CHARS
from src.documents.index import VectorIndex
from src.documents.store import Document, DocumentSet
from src.interview.questions import build_question_request, clean_question
from src.interview.state import Interview, InterviewQuestion
from tests.conftest import fake_embed


def interview(interview_type="hr", language="en", answered=2) -> Interview:
    iv = Interview()
    iv.start(interview_type, language)
    iv.begin_interviewing()
    for i in range(1, answered + 1):
        iv.questions.append(InterviewQuestion(
            index=i, text=f"Question {i}?", asked_at_ms=i * 1000, answer_text=f"My answer number {i}",
        ))
    return iv


def documents_with_references(texts: list[str]) -> DocumentSet:
    docs = DocumentSet()
    docs.index = VectorIndex(lambda ts: [fake_embed(t) for t in ts], fake_embed)
    doc = Document(kind="reference", filename="guide.md", format="md", size_bytes=10, text="x")
    docs.add_reference(doc, texts, index_factory=lambda: docs.index)
    return docs


class TestHR:
    def test_never_contains_answers(self):
        request = build_question_request(interview("hr"), DocumentSet())
        assert request.last_exchange is None
        assert "My answer number" not in repr(request)

    def test_never_gets_passages(self):
        docs = documents_with_references(["Consistent hashing maps keys onto a ring."])
        assert build_question_request(interview("hr"), docs).passages == []


class TestTechnical:
    def test_includes_last_exchange(self):
        request = build_question_request(interview("technical"), DocumentSet())
        assert request.last_exchange == {"question": "Question 2?", "answer": "My answer number 2"}

    def test_passages_at_most_four_and_skip_used(self):
        texts = [f"Passage {i} about hashing number {i}" for i in range(8)]
        docs = documents_with_references(texts)
        iv = interview("technical")
        iv.used_chunk_ids = {0, 1}
        request = build_question_request(iv, docs)
        assert 0 < len(request.passages) <= 4
        assert not set(request.passage_ids) & {0, 1}
        assert request.passages == [texts[i] for i in request.passage_ids]

    def test_no_index_no_passages(self):
        assert build_question_request(interview("technical"), DocumentSet()).passages == []


def test_questions_asked_in_order():
    request = build_question_request(interview("hr", answered=3), DocumentSet())
    assert request.questions_asked == ["Question 1?", "Question 2?", "Question 3?"]


def test_resume_is_capped():
    docs = DocumentSet()
    docs.resume = Document(kind="resume", filename="cv.txt", format="txt", size_bytes=1,
                           text="x" * (RESUME_PROMPT_MAX_CHARS + 500))
    request = build_question_request(interview("hr"), docs)
    assert len(request.resume_text) == RESUME_PROMPT_MAX_CHARS


def test_language_is_carried():
    assert build_question_request(interview("hr", "pt-BR"), DocumentSet()).language == "pt-BR"


class TestCleanQuestion:
    def test_follow_up_prefix(self):
        assert clean_question("FOLLOW-UP: How would it scale?") == ("How would it scale?", True)

    def test_quotes_and_labels(self):
        assert clean_question('Interviewer: "Tell me about a conflict."') == ("Tell me about a conflict.", False)

    def test_empty(self):
        assert clean_question("   ") == ("", False)
