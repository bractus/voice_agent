"""Unit tests for the resume reader (src/interview/resume_reader.py)."""
import asyncio
import json

from src.interview import resume_reader
from src.interview.resume_reader import parse_suggestion, suggest_from_resume


def test_valid():
    assert parse_suggestion(json.dumps({"role": "Backend Engineer", "seniority": "senior"})) == {
        "role": "Backend Engineer", "seniority": "senior",
    }


def test_long_role_is_truncated():
    out = parse_suggestion(json.dumps({"role": "x" * 120, "seniority": "mid"}))
    assert len(out["role"]) == 80


def test_unknown_seniority_becomes_none():
    assert parse_suggestion(json.dumps({"role": "Designer", "seniority": "principal"})) == {
        "role": "Designer", "seniority": None,
    }


def test_malformed_or_empty_is_none():
    assert parse_suggestion("not json") is None
    assert parse_suggestion(json.dumps({"role": None, "seniority": None})) is None
    assert parse_suggestion(json.dumps(["x"])) is None


async def test_timeout_returns_none(monkeypatch):
    async def slow(text):
        await asyncio.sleep(5)
        return json.dumps({"role": "X", "seniority": "mid"})

    monkeypatch.setattr(resume_reader, "_call_model", slow)
    monkeypatch.setattr(resume_reader, "READER_TIMEOUT_SECONDS", 0.1)
    assert await suggest_from_resume("some resume") is None


async def test_errors_return_none(monkeypatch):
    async def boom(text):
        raise RuntimeError("api down")

    monkeypatch.setattr(resume_reader, "_call_model", boom)
    assert await suggest_from_resume("some resume") is None


async def test_empty_text_skips_the_model(monkeypatch):
    called = []

    async def track(text):
        called.append(text)
        return "{}"

    monkeypatch.setattr(resume_reader, "_call_model", track)
    assert await suggest_from_resume("   ") is None
    assert called == []
