"""
Contract tests for the interview flow driven by GPT-Live events
(specs/002-gpt-live-interview/contracts/websocket-protocol.md, data-model.md).

The conductor runs against FakeLiveControl, a fake question writer and a fake
evaluator, so these need no network and no key. Frames the browser would get
are captured from `session.notify`.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from src.api.session_manager import ConversationSession, session_manager
from src.interview import conductor, prompts
from src.interview.questions import QuestionResult, QuestionUnavailableError
from src.interview.state import InterviewStage
from tests import fakes
from tests.fakes import FakeLiveControl


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def fast_timers(monkeypatch):
    monkeypatch.setattr(conductor, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(conductor, "QUIET_SECONDS", 0.05)
    monkeypatch.setattr(conductor, "CLOSE_CAP_SECONDS", 0.5)


# Distinct enough that the duplicate check (difflib ratio ≥ 0.9) never fires.
DISTINCT_QUESTIONS = [
    "Tell me about a project you are proud of?",
    "How do you handle disagreement in a team?",
    "Which database would you pick for an audit log, and why?",
    "What motivates you at work?",
    "Describe a time you missed a deadline.",
    "How would you design a rate limiter?",
]


class Writer:
    """A fake question writer: returns scripted questions and records each call."""

    def __init__(self, monkeypatch, questions: list[str] | None = None, fail: bool = False) -> None:
        self.questions = list(questions or DISTINCT_QUESTIONS)
        self.calls: list[dict] = []
        self.fail = fail
        self.on_call = None
        monkeypatch.setattr(conductor, "write_question", self)

    async def __call__(self, interview, documents) -> QuestionResult:
        self.calls.append({"type": interview.interview_type, "asked": [q.text for q in interview.questions]})
        if self.on_call:
            self.on_call()
        if self.fail:
            raise QuestionUnavailableError("down")
        return QuestionResult(text=self.questions.pop(0), is_follow_up=False, grounded_chunk_ids=[])


class Evaluator:
    def __init__(self, monkeypatch, fail: bool = False) -> None:
        self.calls: list = []
        self.fail = fail
        monkeypatch.setattr(conductor, "run_evaluation", self)

    async def __call__(self, record, resume_text=None, passages_by_index=None) -> dict:
        self.calls.append(record)
        if self.fail:
            raise conductor.EvaluationFailedError("down")
        return {
            "grader": "writer",
            "grader_model": None,
            "writer_model": "gpt-6-sol",
            "per_question": [
                {"index": q["index"], "score": 4.2, "level": 4, "what_worked": "Clear.",
                 "missing": "A number for the result.",
                 "model_answer": "I led [the Checkout migration] and cut the error rate by [40%].",
                 "model_answer_check": None}
                for q in record.questions
            ],
            "overall": {"summary": "Solid.", "strengths": ["Clarity"],
                        "areas_to_improve": [{"text": "Depth", "questions": [1]}]},
        }


class Harness:
    def __init__(self, interview_type: str = "technical", language: str = "en") -> None:
        self.session = ConversationSession(session_id="flow-test")
        self.frames: list[dict] = []

        async def notify(payload: dict) -> None:
            self.frames.append(payload)

        self.session.notify = notify
        self.session.interview.start(interview_type, language)
        self.control = FakeLiveControl()
        self.session.live = self.control
        self.task: asyncio.Task | None = None

    async def start(self) -> Harness:
        self.task = asyncio.create_task(conductor.run(self.session, self.control))
        await self.settle()
        return self

    async def settle(self, seconds: float = 0.03) -> None:
        await asyncio.sleep(seconds)

    async def push(self, *events: dict, settle: float = 0.03) -> None:
        for event in events:
            self.control.push(event)
        await self.settle(settle)

    async def ask(self, delegation_id: str, start_ms: int) -> dict:
        """Delegate, and acknowledge the resulting commentary at start_ms."""
        await self.push(fakes.delegation(delegation_id))
        command = self.control.sent_of_type("session.commentary.append")[-1]
        await self.push(fakes.appended(command["event_id"], start_ms))
        return command

    def of_type(self, kind: str) -> list[dict]:
        return [f for f in self.frames if f["type"] == kind]

    @property
    def stage(self) -> InterviewStage:
        return self.session.interview.stage

    async def wait_finished(self, timeout: float = 2.0) -> None:
        await asyncio.wait_for(self.task, timeout)

    async def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass


@pytest.fixture
async def harness(tmp_interviews_dir):
    created: list[Harness] = []

    async def make(interview_type="technical", language="en") -> Harness:
        h = Harness(interview_type, language)
        created.append(h)
        return await h.start()

    yield make
    for h in created:
        await h.stop()


# ── US1: questions come from the question writer ─────────────────────────────

async def test_delegation_delivers_the_written_question(monkeypatch, harness):
    writer = Writer(monkeypatch, ["What trade-offs did you weigh in the billing service?"])
    h = await harness("technical")

    order: list[str] = []
    writer.on_call = lambda: order.append("writer")
    await h.push(fakes.delegation("d1"))

    assert writer.calls == [{"type": "technical", "asked": []}]
    commentary = h.control.sent_of_type("session.commentary.append")
    assert len(commentary) == 1
    assert commentary[0]["delegation_id"] == "d1"
    assert "«What trade-offs did you weigh in the billing service?»" in commentary[0]["content"]
    assert h.stage == InterviewStage.INTERVIEWING
    # delegation_pending true went out before the writer ran
    pending_index = next(i for i, f in enumerate(h.frames) if f == {"type": "delegation_pending", "pending": True})
    assert pending_index < len(h.frames)

    await h.push(fakes.appended(commentary[0]["event_id"], 5000))
    assert h.of_type("question_asked") == [{"type": "question_asked", "index": 1, "is_follow_up": False}]
    # No question wording reaches the browser (003 FR-010).
    assert not any("billing service" in str(f) for f in h.frames)
    assert h.frames[-1] == {"type": "delegation_pending", "pending": False}
    assert h.session.interview.questions[0].asked_at_ms == 5000


async def test_stage_frame_on_first_delegation(monkeypatch, harness):
    Writer(monkeypatch)
    h = await harness("hr", "pt-BR")
    await h.push(fakes.delegation("d1"))
    stage = h.of_type("interview_stage")[-1]
    assert stage["stage"] == "interviewing"
    assert (stage["interview_type"], stage["language"]) == ("hr", "pt-BR")


async def test_writer_failure_is_reported_and_interview_continues(monkeypatch, harness):
    Writer(monkeypatch, fail=True)
    h = await harness()
    await h.push(fakes.delegation("d1"))
    assert h.of_type("error")[-1]["code"] == "QUESTION_UNAVAILABLE"
    instructions = [c["content"] for c in h.control.sent_of_type("session.instructions.append")]
    assert any("isn't ready" in text for text in instructions)
    assert h.session.interview.is_active


async def test_delegation_after_conclusion_is_ignored(monkeypatch, harness):
    writer = Writer(monkeypatch)
    h = await harness()
    h.session.requests.put_nowait(("end", "end_button"))
    await h.settle(0.2)
    await h.wait_finished()
    calls = len(writer.calls)
    h.control.push(fakes.delegation("late"))
    await h.settle()
    assert len(writer.calls) == calls


# ── US2: greeting, and no question before readiness ──────────────────────────

async def test_greeting_sent_once(monkeypatch, harness):
    Writer(monkeypatch)
    h = await harness()
    await h.push(fakes.started(), fakes.started())
    greetings = [c for c in h.control.sent_of_type("session.instructions.append")
                 if c["content"] == prompts.GREETING_INSTRUCTION]
    assert len(greetings) == 1


async def test_no_question_without_delegation(monkeypatch, harness):
    writer = Writer(monkeypatch)
    h = await harness()
    await h.push(fakes.started(), fakes.user_says("yes I'm ready", 1000))
    assert writer.calls == []
    assert h.stage == InterviewStage.INTRODUCING


# ── US3: endings, errors, inactivity, prefetch ───────────────────────────────

async def test_stop_phrase_ends_with_goodbye_then_close(monkeypatch, harness):
    Writer(monkeypatch)
    Evaluator(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("okay let's end the interview", 2000))

    assert h.of_type("interview_stage")[-1]["stage"] in ("concluding", "concluded")
    assert h.control.sent_of_type("session.instructions.append")[-1]["content"] == prompts.CONCLUDE_INSTRUCTION
    await h.push(fakes.interviewer_says("Thanks for your time, goodbye!", 2600))
    await h.wait_finished()
    assert h.control.sent_of_type("session.close")
    assert h.stage == InterviewStage.CONCLUDED
    assert h.session.interview.end_reason == "user_request"
    assert h.of_type("interview_stage")[-1]["end_reason"] == "user_request"


async def test_bare_stop_does_not_end(monkeypatch, harness):
    Writer(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("if the queue is full the producer will stop", 2000))
    assert h.session.interview.is_active


async def test_portuguese_stop_phrase(monkeypatch, harness):
    Writer(monkeypatch)
    Evaluator(monkeypatch)
    h = await harness("hr", "pt-BR")
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("tudo bem, vamos encerrar a entrevista", 2000))
    assert h.session.interview.end_reason == "user_request"


async def test_end_button(monkeypatch, harness):
    Writer(monkeypatch)
    Evaluator(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    h.session.requests.put_nowait(("end", "end_button"))
    await h.wait_finished()
    assert h.session.interview.end_reason == "end_button"
    assert h.control.sent_of_type("session.close")


@pytest.mark.parametrize("how", ["closed", "browser"])
async def test_lost_connection(monkeypatch, harness, how):
    Writer(monkeypatch)
    Evaluator(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    if how == "closed":
        h.control.drop()
    else:
        h.session.requests.put_nowait(("end", "connection_lost"))
    await h.wait_finished()
    assert h.of_type("error")[-1]["code"] == "LIVE_SESSION_LOST"
    assert h.session.interview.end_reason == "connection_lost"
    assert h.stage == InterviewStage.CONCLUDED
    assert not h.control.sent_of_type("session.instructions.append")[1:] or all(
        c["content"] != prompts.CONCLUDE_INSTRUCTION for c in h.control.sent_of_type("session.instructions.append")
    )


async def test_unrelated_error_is_not_fatal(monkeypatch, harness):
    Writer(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.error("unknown_parameter", client_event_id="someone-else"))
    assert h.session.interview.is_active
    assert not h.of_type("error")


async def test_commentary_error_is_retried_once(monkeypatch, harness):
    Writer(monkeypatch)
    h = await harness()
    await h.push(fakes.delegation("d1"))
    first = h.control.sent_of_type("session.commentary.append")[-1]
    await h.push(fakes.error("rejected", client_event_id=first["event_id"]))
    retries = h.control.sent_of_type("session.commentary.append")
    assert len(retries) == 2 and retries[1]["content"] == first["content"]
    await h.push(fakes.error("rejected", client_event_id=retries[1]["event_id"]))
    assert h.of_type("error")[-1]["code"] == "QUESTION_UNAVAILABLE"
    assert h.session.interview.is_active


async def test_inactivity_ends_after_three_minutes(monkeypatch, harness):
    Writer(monkeypatch)
    Evaluator(monkeypatch)
    clock = FakeClock()
    monkeypatch.setattr(conductor, "clock", clock)
    h = await harness()
    await h.ask("d1", 1000)

    clock.now += 100
    await h.push(fakes.user_says("so I think", 2000))      # restarts the count
    clock.now += 179
    await h.settle()
    assert h.session.interview.is_active

    clock.now += 1
    await h.settle()
    assert h.session.interview.end_reason == "inactivity"
    assert h.control.sent_of_type("session.instructions.append")[-1]["content"] == prompts.INACTIVITY_INSTRUCTION
    clock.now += 11                                        # goodbye cap, then close
    await h.settle(0.1)
    await h.wait_finished()
    assert h.stage == InterviewStage.CONCLUDED


async def test_check_in_resets_the_timer_only_once(monkeypatch, harness):
    Writer(monkeypatch)
    clock = FakeClock()
    monkeypatch.setattr(conductor, "clock", clock)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.interviewer_says("What trade-offs?", 1100))   # the question itself

    clock.now += 60
    await h.push(fakes.interviewer_says("Take your time.", 60000))    # check-in: resets once
    clock.now += 120
    await h.push(fakes.interviewer_says("No rush.", 180000))          # second check-in: no reset
    clock.now += 61                                                    # 181 s since the first check-in
    await h.settle()
    assert h.session.interview.end_reason == "inactivity"


# ── Answer end: the conductor nudges a quiet interviewer (research.md §7) ─────

def _nudges(h: Harness) -> list[str]:
    nudges = (prompts.ANSWER_END_INSTRUCTION, prompts.DONE_INSTRUCTION, prompts.READY_CHECK_INSTRUCTION)
    return [c["content"] for c in h.control.sent_of_type("session.instructions.append") if c["content"] in nudges]


async def _asked(monkeypatch, harness, language="en") -> tuple[Harness, FakeClock]:
    Writer(monkeypatch)
    clock = FakeClock()
    monkeypatch.setattr(conductor, "clock", clock)
    h = await harness("technical", language)
    await h.push(fakes.user_says("I'm ready", 500))
    await h.ask("d1", 1000)
    await h.push(fakes.interviewer_says("What trade-offs?", 1000))
    clock.now += 1                                           # the candidate speaks after the question
    return h, clock


async def test_silence_after_an_answer_nudges_once(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    await h.push(fakes.user_says("I would use a queue so writes never block", 3000))
    clock.now += 3.9
    await h.settle()
    assert _nudges(h) == []

    clock.now += 0.1
    await h.settle()
    assert _nudges(h) == [prompts.ANSWER_END_INSTRUCTION]
    clock.now += 30
    await h.settle()
    assert _nudges(h) == [prompts.ANSWER_END_INSTRUCTION]   # one per silence

    await h.push(fakes.user_says("and retry on failure", 40000))   # speaking again re-arms it
    clock.now += 4
    await h.settle()
    assert _nudges(h) == [prompts.ANSWER_END_INSTRUCTION] * 2
    assert h.session.interview.is_active


async def test_done_phrase_nudges_after_a_short_pause(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness, "pt-BR")
    await h.push(fakes.user_says("Eu usaria uma fila. É isso, pronto.", 3000))
    clock.now += 0.5
    await h.settle()
    assert _nudges(h) == []
    clock.now += 0.5
    await h.settle()
    assert _nudges(h) == [prompts.DONE_INSTRUCTION]


async def test_no_nudge_before_the_candidate_speaks(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    clock.now += 60
    await h.settle()
    assert _nudges(h) == []


async def test_no_nudge_when_the_interviewer_took_its_turn(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    await h.push(fakes.user_says("Can you repeat the question?", 3000))
    clock.now += 1
    await h.push(fakes.interviewer_says("Sure. What trade-offs?", 4000))
    clock.now += 10
    await h.settle()
    assert _nudges(h) == []


async def test_no_nudge_while_a_question_is_pending(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    await h.push(fakes.user_says("I would use a queue", 3000))
    h.session.interview.pending_delegation_id = "d2"        # the interviewer already delegated
    clock.now += 10
    await h.settle()
    assert _nudges(h) == []


async def test_no_nudge_while_muted(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    await h.push(fakes.user_says("I would use a queue", 3000))
    h.session.requests.put_nowait(("mute", True))
    clock.now += 10
    await h.settle()
    assert _nudges(h) == []
    h.session.requests.put_nowait(("mute", False))
    await h.settle()
    assert _nudges(h) == [prompts.ANSWER_END_INSTRUCTION]


async def test_readiness_silence_gets_a_ready_check(monkeypatch, harness):
    Writer(monkeypatch)
    clock = FakeClock()
    monkeypatch.setattr(conductor, "clock", clock)
    h = await harness()
    await h.push(fakes.started(), fakes.interviewer_says("Are you ready to begin?", 100))
    clock.now += 1
    await h.push(fakes.user_says("Yes, let's go", 2000))
    clock.now += 4
    await h.settle()
    assert _nudges(h) == [prompts.READY_CHECK_INSTRUCTION]


async def test_a_new_question_resets_the_answer_state(monkeypatch, harness):
    h, clock = await _asked(monkeypatch, harness)
    await h.push(fakes.user_says("I would use a queue. That's it.", 3000))
    await h.ask("d2", 6000)                                  # delegated before any nudge
    clock.now += 10
    await h.settle()
    assert _nudges(h) == []


async def test_hr_prefetch(monkeypatch, harness):
    writer = Writer(monkeypatch)
    h = await harness("hr")
    await h.ask("d1", 1000)
    assert len(writer.calls) == 2              # question 1, then the prefetch of question 2
    await h.push(fakes.user_says("I led a team of five.", 2000))
    await h.push(fakes.delegation("d2"))
    assert len(writer.calls) == 2              # delivered from the prefetch
    assert f"«{DISTINCT_QUESTIONS[1]}»" in h.control.sent_of_type("session.commentary.append")[-1]["content"]


async def test_technical_never_prefetches(monkeypatch, harness):
    writer = Writer(monkeypatch)
    h = await harness("technical")
    await h.ask("d1", 1000)
    assert len(writer.calls) == 1


# ── US4: answers saved, evaluation ───────────────────────────────────────────

async def test_answer_saved_before_next_question(monkeypatch, harness, tmp_interviews_dir):
    writer = Writer(monkeypatch)
    h = await harness("technical")
    await h.ask("d1", 1000)
    await h.push(fakes.interviewer_says("Tell me about a project you are proud of?", 1000), fakes.user_says("I would use", 2000),
                 fakes.user_says(" a queue.", 2500))

    folder = tmp_interviews_dir / h.session.interview.interview_id
    seen: list[str] = []
    writer.on_call = lambda: seen.append((folder / "transcript.md").read_text())
    await h.push(fakes.delegation("d2"))

    assert h.of_type("answer_saved") == [{"type": "answer_saved", "index": 1}]
    assert "I would use a queue." in seen[0]
    record = json.loads((folder / "record.json").read_text())
    assert record["questions"][0]["answer_text"] == "I would use a queue."
    assert record["questions"][0]["spoken_text"] == "Tell me about a project you are proud of?"


async def test_report_ready(monkeypatch, harness, tmp_interviews_dir):
    Writer(monkeypatch)
    evaluator = Evaluator(monkeypatch)
    h = await harness("hr")
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("I led a team.", 2000))
    h.session.requests.put_nowait(("end", "end_button"))
    await h.wait_finished()

    statuses = [f["status"] for f in h.of_type("report_status")]
    assert statuses == ["pending", "ready"]
    assert h.of_type("report_status")[-1]["interview_id"] == h.session.interview.interview_id
    folder = tmp_interviews_dir / h.session.interview.interview_id
    assert (folder / "report.md").is_file()
    assert json.loads((folder / "record.json").read_text())["report_status"] == "ready"
    assert len(evaluator.calls) == 1


async def test_nothing_to_evaluate(monkeypatch, harness):
    Writer(monkeypatch)
    evaluator = Evaluator(monkeypatch)
    h = await harness()
    h.session.requests.put_nowait(("end", "end_button"))
    await h.wait_finished()
    assert [f["status"] for f in h.of_type("report_status")] == ["skipped"]
    assert evaluator.calls == []


async def test_evaluation_failure(monkeypatch, harness, tmp_interviews_dir):
    Writer(monkeypatch)
    Evaluator(monkeypatch, fail=True)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("An answer.", 2000))
    h.session.requests.put_nowait(("end", "end_button"))
    await h.wait_finished()
    last = h.of_type("report_status")[-1]
    assert last["status"] == "failed"
    assert last["message"] == conductor.EVALUATION_FAILED_MESSAGE
    assert (tmp_interviews_dir / h.session.interview.interview_id / "transcript.md").is_file()


async def test_connection_lost_is_evaluated(monkeypatch, harness):
    Writer(monkeypatch)
    evaluator = Evaluator(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("First answer.", 2000))
    await h.ask("d2", 3000)
    await h.push(fakes.user_says("Second answer.", 4000))
    h.control.drop()
    await h.wait_finished()
    assert len(evaluator.calls) == 1
    assert [f["status"] for f in h.of_type("report_status")][-1] == "ready"


async def test_page_closed_saves_but_does_not_evaluate(monkeypatch, harness, tmp_interviews_dir):
    Writer(monkeypatch)
    evaluator = Evaluator(monkeypatch)
    h = await harness()
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("Half an answer", 2000))
    await h.session.shutdown()
    await h.settle()
    record = json.loads((tmp_interviews_dir / h.session.interview.interview_id / "record.json").read_text())
    assert record["end_reason"] == "page_closed"
    assert record["questions"][0]["answer_text"] == "Half an answer"
    assert evaluator.calls == []
    assert h.control.closed


async def test_portuguese_interview_asks_evaluator_for_portuguese(monkeypatch, harness):
    from src.evaluation.prompts import build_writer_header

    Writer(monkeypatch)
    evaluator = Evaluator(monkeypatch)
    h = await harness("hr", "pt-BR")
    await h.ask("d1", 1000)
    await h.push(fakes.user_says("Liderei um time.", 2000))
    h.session.requests.put_nowait(("end", "end_button"))
    await h.wait_finished()
    assert "Brazilian Portuguese" in build_writer_header(evaluator.calls[0], None)


# ── App WebSocket frames ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    from src.app import app
    return TestClient(app)


def test_end_interview_in_setup_is_invalid(client):
    with client.websocket_connect("/ws/ws-frames") as ws:
        assert ws.receive_json()["type"] == "session_created"
        assert ws.receive_json()["stage"] == "setup"
        ws.send_json({"type": "end_interview"})
        frame = ws.receive_json()
        assert (frame["type"], frame["code"]) == ("error", "INVALID_STAGE")


def test_end_interview_and_live_disconnected_are_queued(client):
    with client.websocket_connect("/ws/ws-queue") as ws:
        ws.receive_json(), ws.receive_json()
        session = session_manager.get("ws-queue")
        session.interview.start("hr")
        ws.send_json({"type": "end_interview"})
        ws.send_json({"type": "live_disconnected"})
        ws.send_json({"type": "start_session"})  # a round trip, so the frames above are processed
        import time
        time.sleep(0.1)
        requests = []
        while not session.requests.empty():
            requests.append(session.requests.get_nowait())
        assert ("end", "end_button") in requests
        assert ("end", "connection_lost") in requests
