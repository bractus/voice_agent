"""
The grader (src/evaluation/grader.py, specs/004 contracts/grader.md), against a fake HTTP
transport: nothing reaches OpenRouter.
"""
from __future__ import annotations

import json

import httpx
import pytest

from src import config, openrouter_client
from src.evaluation import grader
from src.evaluation.grader import GraderUnavailableError, build_grade_request, grade_answer, parse_grade_response
from src.evaluation.prompts import GRADE_LEVELS
from src.interview.record import InterviewRecord

HR_IDS = ["answers_exact_question", "concrete_situation", "own_actions", "measurable_result", "reflection", "level_fit"]


def record(interview_type="hr") -> InterviewRecord:
    return InterviewRecord(interview_id="20260926-124939-hr-1buota", interview_type=interview_type,
                           language="pt-BR", started_at="2026-09-26T12:49:39+00:00", role="Data Engineer")


QUESTION = {"index": 1, "text": "Como você prioriza demandas?"}


def reply(score=1.31, probabilities=None, noul=None, model="typesafe/jev-1.13-20260917") -> dict:
    probabilities = probabilities or {"0": 0.12, "1": 0.72, "2": 0.15, "3": 0.01, "4": 0, "5": 0}
    noul = noul if noul is not None else {i: 0.9 for i in HR_IDS}
    answers = {"grade": {"type": "score", "score": score, "probabilities": probabilities, "confidence": 0.77}}
    answers.update({i: {"type": "noul", "noul": v} for i, v in noul.items()})
    return {"model": model, "answers": answers, "usage": {"cost": 0.00002}}


@pytest.fixture
def transport(monkeypatch):
    """Install a scripted transport; returns the list of requests it saw and the queue of responses."""
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(grader, "GRADER_TIMEOUT_SECONDS", 0.5)
    seen: list[httpx.Request] = []
    script: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(base_url=openrouter_client.OPENROUTER_BASE_URL,
                               headers={"Authorization": "Bearer sk-or-test"},
                               transport=httpx.MockTransport(handler))
    monkeypatch.setattr(openrouter_client, "_client", client)
    return seen, script


# ── Request ───────────────────────────────────────────────────────────────────

def test_request_shape():
    body = build_grade_request(record(), QUESTION, "Eu alinho com meu gestor.")
    assert body["model"] == config.OPENROUTER_GRADER_MODEL
    assert body["state"] == {"interview": "HR (behavioral)", "position": "a mid-level «Data Engineer» position",
                             "question": "Como você prioriza demandas?", "answer": "Eu alinho com meu gestor."}
    assert body["questions"]["grade"]["type"] == "score"
    assert body["questions"]["grade"]["criteria"] == GRADE_LEVELS
    assert list(body["questions"])[1:] == HR_IDS
    assert all(body["questions"][i]["type"] == "noul" for i in HR_IDS)


def test_technical_request_with_passages():
    body = build_grade_request(record("technical"), QUESTION, "", ["Queues decouple producers."])
    assert body["state"]["answer"] == "(no answer)"
    assert body["state"]["reference_passages"] == ["Queues decouple producers."]
    assert list(body["questions"])[-1] == "consistent_with_reference"
    assert "concrete_situation" not in body["questions"]


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_score_is_kept_as_returned():
    result = parse_grade_response(reply(1.31), HR_IDS)
    assert result.score == 1.31 and result.level == 1
    assert result.probabilities[1] == 0.72 and result.confidence == 0.77
    assert result.model == "typesafe/jev-1.13-20260917"


def test_gaps_are_the_failing_diagnostics_in_rubric_order():
    noul = {i: 0.9 for i in HR_IDS} | {"reflection": 0.2, "concrete_situation": 0.49, "own_actions": 0.5}
    assert parse_grade_response(reply(noul=noul), HR_IDS).gaps == ["concrete_situation", "reflection"]


def test_ties_go_to_the_lower_level():
    probabilities = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0.5, "5": 0.5}
    assert parse_grade_response(reply(4.5, probabilities), HR_IDS).level == 4


@pytest.mark.parametrize("data", [
    reply(score=5.2),
    reply(score="3"),
    reply(probabilities={"0": 0.5, "1": 0.5}),
    reply(noul={i: 0.9 for i in HR_IDS[:-1]}),
    reply(noul={i: 1.4 for i in HR_IDS}),
    {"answers": {}},
    {},
])
def test_malformed_replies(data):
    with pytest.raises(GraderUnavailableError):
        parse_grade_response(data, HR_IDS)


# ── Calls ─────────────────────────────────────────────────────────────────────

async def test_a_graded_call(transport):
    seen, script = transport
    script.append((200, reply()))
    result = await grade_answer(record(), QUESTION, "Eu alinho com meu gestor.")
    assert result.score == 1.31
    assert seen[0].url.path == "/api/alpha/decisions"
    assert json.loads(seen[0].content)["state"]["answer"] == "Eu alinho com meu gestor."


async def test_no_key_means_no_request(transport, monkeypatch):
    seen, _ = transport
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with pytest.raises(GraderUnavailableError):
        await grade_answer(record(), QUESTION, "x")
    assert seen == []


async def test_a_rejected_key_is_not_retried(transport):
    seen, script = transport
    script.append((401, {"error": {"message": "No auth credentials found", "code": 401}}))
    with pytest.raises(GraderUnavailableError):
        await grade_answer(record(), QUESTION, "x")
    assert len(seen) == 1


async def test_a_timeout_is_retried_once(transport):
    seen, script = transport
    script += [httpx.ReadTimeout("slow"), (200, reply())]
    assert (await grade_answer(record(), QUESTION, "x")).score == 1.31
    assert len(seen) == 2


async def test_a_malformed_reply_is_retried_once(transport):
    seen, script = transport
    script += [(200, {"answers": {}}), (200, reply())]
    assert (await grade_answer(record(), QUESTION, "x")).level == 1
    assert len(seen) == 2


async def test_two_server_errors_give_up(transport):
    seen, script = transport
    script += [(503, {}), (503, {})]
    with pytest.raises(GraderUnavailableError):
        await grade_answer(record(), QUESTION, "x")
    assert len(seen) == 2


def test_client_headers(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "sk-or-abc")
    openrouter_client.reset_client()
    try:
        client = openrouter_client.get_openrouter_client()
        assert client.headers["Authorization"] == "Bearer sk-or-abc"
        assert client.headers["X-OpenRouter-Title"] == "Dev Fairy"
    finally:
        openrouter_client.reset_client()


def test_error_descriptions_carry_no_body():
    request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
    response = httpx.Response(401, request=request, json={"error": "sk-or-secret"})
    exc = httpx.HTTPStatusError("bad sk-or-secret", request=request, response=response)
    assert openrouter_client.describe_http_error(exc) == "HTTPStatusError(401)"
