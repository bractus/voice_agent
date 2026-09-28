"""
The API key never leaves the server (FR-010, SC-006).

Runs the whole flow with a sentinel key: status → start → two questions → end →
report, including a creation failure whose error message contains the key. The
sentinel must not appear in any HTTP response, WebSocket frame or log record.
"""
from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.interview import conductor
from src.live.session import LiveUnavailableError
from tests import fakes
from tests.contract.test_websocket_interview import DISTINCT_QUESTIONS, Evaluator, Harness, Writer
from tests.fakes import FakeLiveControl

SENTINEL = "sk-test-SENTINEL-do-not-leak"


@pytest.fixture
def sentinel_key(monkeypatch, caplog):
    monkeypatch.setattr("src.config.OPENAI_API_KEY", SENTINEL)
    monkeypatch.setattr("src.openai_client._async_client", None)
    monkeypatch.setattr("src.openai_client._sync_client", None)
    monkeypatch.setattr("src.openai_client._status_cache", None)
    caplog.set_level(logging.DEBUG)
    return caplog


def assert_clean(*texts: str, caplog) -> None:
    for text in texts:
        assert SENTINEL not in text
    for record in caplog.records:
        assert SENTINEL not in record.getMessage()
        assert SENTINEL not in str(record.args)


def test_http_and_frames_never_carry_the_key(sentinel_key, monkeypatch):
    caplog = sentinel_key

    async def check():
        return "ok"

    attempts: list[int] = []

    async def create(session_config, sdp):
        attempts.append(1)
        if len(attempts) == 1:
            # A failure whose message contains the key must not leak it.
            logging.getLogger("src.live.session").error("GPT-Live session creation failed: %s", "AuthenticationError(401)")
            raise LiveUnavailableError(f"bad key {SENTINEL}")
        return "v=0 answer", "sess_1"

    async def attach(live_session_id, send_text):
        return FakeLiveControl(live_session_id)

    async def idle_run(session, control):
        pass

    monkeypatch.setattr("src.openai_client.check_openai", check)
    monkeypatch.setattr("src.live.session.create_live_session", create)
    monkeypatch.setattr("src.live.control.attach_control", attach)
    monkeypatch.setattr(conductor, "run", idle_run)

    from src.app import app
    client = TestClient(app)
    seen: list[str] = []
    with client.websocket_connect("/ws/leak-test") as ws:
        seen += [json.dumps(ws.receive_json()), json.dumps(ws.receive_json())]
        for _ in range(2):
            res = client.post("/api/sessions/leak-test/live", json={"interview_type": "hr", "sdp": "v=0 offer"})
            seen += [res.text, json.dumps(dict(res.headers))]
        seen.append(json.dumps(ws.receive_json()))
        res = client.get("/api/status")
        seen += [res.text, json.dumps(dict(res.headers))]
    assert_clean(*seen, caplog=caplog)


async def test_interview_flow_never_carries_the_key(sentinel_key, monkeypatch, tmp_interviews_dir):
    caplog = sentinel_key
    monkeypatch.setattr(conductor, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(conductor, "QUIET_SECONDS", 0.05)
    monkeypatch.setattr(conductor, "CLOSE_CAP_SECONDS", 0.5)
    Writer(monkeypatch)
    Evaluator(monkeypatch)

    h = Harness("technical")
    await h.start()
    try:
        await h.push(fakes.started())
        await h.ask("d1", 1000)
        await h.push(fakes.user_says("First answer.", 2000))
        await h.ask("d2", 3000)
        await h.push(fakes.user_says("Second answer.", 4000))
        h.session.requests.put_nowait(("end", "end_button"))
        await h.wait_finished()
    finally:
        await h.stop()

    assert [f["status"] for f in h.of_type("report_status")][-1] == "ready"
    files = [p.read_text() for p in tmp_interviews_dir.rglob("*") if p.is_file()]
    assert_clean(*(json.dumps(f) for f in h.frames), *(json.dumps(c) for c in h.control.sent), *files, caplog=caplog)
    assert DISTINCT_QUESTIONS  # the shared fixtures are importable


OR_SENTINEL = "sk-or-test-SENTINEL-do-not-leak"


async def test_grader_errors_never_carry_the_openrouter_key(monkeypatch, caplog, tmp_interviews_dir):
    """specs/004 FR-015: the grader rejects the key and echoes it back; it must go nowhere."""
    import httpx

    from src import openrouter_client
    from src.evaluation import evaluator

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr("src.config.OPENROUTER_API_KEY", OR_SENTINEL)
    monkeypatch.setattr(conductor, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(conductor, "QUIET_SECONDS", 0.05)
    monkeypatch.setattr(conductor, "CLOSE_CAP_SECONDS", 0.5)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"rejected {request.headers['Authorization']}"}})

    monkeypatch.setattr(openrouter_client, "_client", httpx.AsyncClient(
        base_url=openrouter_client.OPENROUTER_BASE_URL, headers={"Authorization": f"Bearer {OR_SENTINEL}"},
        transport=httpx.MockTransport(handler)))

    async def fake_writer(name, instructions, input_text, schema):
        if name == "overall":
            return {"summary": "Solid.", "strengths": ["Clarity"], "areas_to_improve": []}
        return {"what_worked": "Clear.", "missing": "A number.", "model_answer": "I shipped [Checkout].", "rating": 3}

    monkeypatch.setattr(evaluator, "_call_writer", fake_writer)
    Writer(monkeypatch)

    h = Harness("hr")
    await h.start()
    try:
        await h.push(fakes.started())
        await h.ask("d1", 1000)
        await h.push(fakes.user_says("First answer.", 2000))
        h.session.requests.put_nowait(("end", "end_button"))
        await h.wait_finished()
    finally:
        await h.stop()

    assert [f["status"] for f in h.of_type("report_status")][-1] == "ready"
    report = json.loads(next(tmp_interviews_dir.rglob("report.json")).read_text())
    assert report["grader"] == "writer"   # the rejected key fell back, it didn't fail
    files = [p.read_text() for p in tmp_interviews_dir.rglob("*") if p.is_file()]
    texts = [*(json.dumps(f) for f in h.frames), *files]
    for text in texts:
        assert OR_SENTINEL not in text
    for record in caplog.records:
        assert OR_SENTINEL not in record.getMessage()
        assert OR_SENTINEL not in str(record.args)
