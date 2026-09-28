"""The resume reader against the real model. Skipped without OPENAI_API_KEY."""
from pathlib import Path

import pytest

from src.documents.extract import extract_text
from src.interview.resume_reader import suggest_from_resume
from tests.integration import requires_openai

FIXTURES = Path(__file__).parent.parent / "fixtures"

pytestmark = [pytest.mark.integration, requires_openai]


async def test_fixture_resume_gives_a_role():
    text = extract_text((FIXTURES / "resume.pdf").read_bytes(), "resume.pdf")
    suggestion = await suggest_from_resume(text)
    assert suggestion is not None
    assert suggestion["role"]
    assert suggestion["seniority"] in ("junior", "mid", "senior", None)
