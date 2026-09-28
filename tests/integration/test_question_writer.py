"""The question writer against the real model (gpt-6-luna). Skipped without OPENAI_API_KEY."""
from pathlib import Path

import pytest

from src.documents.extract import extract_text
from src.documents.index import VectorIndex
from src.documents.store import Document, DocumentSet
from src.interview.questions import write_question
from src.interview.state import Interview, InterviewQuestion
from tests.conftest import fake_embed
from tests.integration import requires_openai

FIXTURES = Path(__file__).parent.parent / "fixtures"

pytestmark = [pytest.mark.integration, requires_openai]


def interview(interview_type: str, language: str = "en") -> Interview:
    iv = Interview()
    iv.start(interview_type, language)
    iv.begin_interviewing()
    return iv


def is_one_question(text: str) -> bool:
    sentences = [s for s in text.replace("?", "?|").replace(".", ".|").split("|") if s.strip()]
    return text.strip().endswith("?") and len(sentences) <= 2


async def test_hr_question_from_resume():
    docs = DocumentSet()
    text = extract_text((FIXTURES / "resume.pdf").read_bytes(), "resume.pdf")
    docs.resume = Document(kind="resume", filename="resume.pdf", format="pdf", size_bytes=1, text=text)
    result = await write_question(interview("hr"), docs)
    assert is_one_question(result.text), result.text
    assert not result.is_follow_up
    assert "FOLLOW-UP" not in result.text


async def test_technical_question_grounded_in_passages():
    docs = DocumentSet()
    docs.index = VectorIndex(lambda ts: [fake_embed(t) for t in ts], fake_embed)
    passages = ["Raft elects a leader with randomized election timeouts; the leader replicates its log to followers."]
    doc = Document(kind="reference", filename="raft.md", format="md", size_bytes=1, text=passages[0])
    docs.add_reference(doc, passages, index_factory=lambda: docs.index)
    result = await write_question(interview("technical"), docs)
    assert is_one_question(result.text), result.text


async def test_portuguese_question():
    iv = interview("hr", "pt-BR")
    iv.questions.append(InterviewQuestion(index=1, text="Tell me about yourself?", asked_at_ms=0, answer_text="..."))
    result = await write_question(iv, DocumentSet())
    assert result.text.strip().endswith("?")
    # A Portuguese question uses Portuguese function words.
    assert any(w in f" {result.text.lower()} " for w in (" você ", " de ", " que ", " como ", " uma ", " um ")), result.text
