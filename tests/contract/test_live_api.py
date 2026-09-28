"""Contract tests for POST /api/sessions/{id}/live and GET /api/status
(specs/002-gpt-live-interview/contracts/http-api.md)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.session_manager import session_manager
from src.interview import conductor
from src.live.session import LiveUnavailableError
from tests.fakes import FakeLiveControl

ANSWER = "v=0\r\no=- answer"


@pytest.fixture
def client():
    from src.app import app
    return TestClient(app)


@pytest.fixture
def live(monkeypatch, openai_ok):
    """Fake GPT-Live session creation and control plane; captures the session config."""
    created: list[dict] = []

    async def create(session_config, sdp):
        created.append(session_config)
        return ANSWER, "sess_123"

    async def attach(live_session_id, send_text):
        return FakeLiveControl(live_session_id)

    async def idle_run(session, control):
        pass

    monkeypatch.setattr("src.live.session.create_live_session", create)
    monkeypatch.setattr("src.live.control.attach_control", attach)
    monkeypatch.setattr(conductor, "run", idle_run)
    return created


def post(client, session_id="live-test", **body):
    payload = {"interview_type": "technical", "sdp": "v=0\r\no=- offer"}
    payload.update(body)
    return client.post(f"/api/sessions/{session_id}/live", json={k: v for k, v in payload.items() if v is not None})


def test_start_returns_answer_and_announces_stage(client, live):
    with client.websocket_connect("/ws/live-test") as ws:
        ws.receive_json(), ws.receive_json()
        res = post(client, language="pt-BR")
        assert res.status_code == 201
        body = res.json()
        assert body["sdp"] == ANSWER
        assert body["live_session_id"] == "sess_123"
        stage = ws.receive_json()
        assert stage["type"] == "interview_stage"
        assert stage["stage"] == "introducing"
        assert (stage["interview_type"], stage["language"]) == ("technical", "pt-BR")
        assert stage["interview_id"] == body["interview_id"]
        instructions = live[0]["instructions"]
        assert "Brazilian Portuguese" in instructions
        assert live[0]["delegation"] == {"type": "client"}


def test_language_defaults_to_english(client, live):
    with client.websocket_connect("/ws/live-test"):
        assert post(client).status_code == 201
        assert session_manager.get("live-test").interview.language == "en"


@pytest.mark.parametrize("body,code", [
    ({"interview_type": None}, "INVALID_INTERVIEW_TYPE"),
    ({"interview_type": "sales"}, "INVALID_INTERVIEW_TYPE"),
    ({"language": "fr"}, "INVALID_LANGUAGE"),
    ({"sdp": ""}, "INVALID_SDP"),
])
def test_validation(client, live, body, code):
    with client.websocket_connect("/ws/live-test"):
        res = post(client, **body)
        assert res.status_code == 422
        assert res.json()["code"] == code and res.json()["message"]
        assert session_manager.get("live-test").interview.stage.value == "setup"


def test_second_start_is_409(client, live):
    with client.websocket_connect("/ws/live-test"):
        assert post(client).status_code == 201
        res = post(client)
        assert res.status_code == 409
        assert res.json()["code"] == "INTERVIEW_STARTED"


def test_unknown_session_is_404(client, live):
    res = post(client, session_id="nobody")
    assert res.status_code == 404
    assert res.json()["code"] == "SESSION_NOT_FOUND"


@pytest.mark.parametrize("status,code", [
    ("missing_key", "OPENAI_NOT_CONFIGURED"),
    ("model_unavailable", "OPENAI_NOT_CONFIGURED"),
    ("unavailable", "OPENAI_UNAVAILABLE"),
])
def test_openai_not_ready(client, live, monkeypatch, status, code):
    async def check():
        return status
    monkeypatch.setattr("src.openai_client.check_openai", check)
    with client.websocket_connect("/ws/live-test"):
        res = post(client)
        assert res.status_code == 503
        assert res.json()["code"] == code


def test_creation_failure_leaves_setup(client, live, monkeypatch):
    async def fail(session_config, sdp):
        raise LiveUnavailableError("down")
    monkeypatch.setattr("src.live.session.create_live_session", fail)
    with client.websocket_connect("/ws/live-test"):
        res = post(client)
        assert res.status_code == 503
        assert res.json()["code"] == "OPENAI_UNAVAILABLE"
        assert session_manager.get("live-test").interview.stage.value == "setup"


def test_status_endpoint(client, monkeypatch):
    async def check():
        return "invalid_key"
    monkeypatch.setattr("src.openai_client.check_openai", check)
    body = client.get("/api/status").json()
    assert body["openai"] == "invalid_key"
    assert "rejected" in body["message"]
    assert client.get("/health").json()["openai"] == "invalid_key"


def test_role_and_seniority_reach_stage_and_instructions(client, live):
    with client.websocket_connect("/ws/live-test") as ws:
        ws.receive_json(), ws.receive_json()
        res = post(client, role="  Backend Engineer ", seniority="senior")
        assert res.status_code == 201
        stage = ws.receive_json()
        assert (stage["role"], stage["seniority"]) == ("Backend Engineer", "senior")
        assert "senior «Backend Engineer» position" in live[0]["instructions"]


def test_role_and_seniority_defaults(client, live):
    with client.websocket_connect("/ws/live-test"):
        assert post(client).status_code == 201
        iv = session_manager.get("live-test").interview
        assert (iv.role, iv.seniority) == (None, "mid")


@pytest.mark.parametrize("body,code", [
    ({"role": "x" * 81}, "INVALID_ROLE"),
    ({"seniority": "lead"}, "INVALID_SENIORITY"),
])
def test_role_and_seniority_validation(client, live, body, code):
    with client.websocket_connect("/ws/live-test"):
        res = post(client, **body)
        assert res.status_code == 422
        assert res.json()["code"] == code and res.json()["message"]
