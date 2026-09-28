"""
Interview conductor — drives one interview from the GPT-Live event stream
(specs/002-gpt-live-interview/data-model.md, research.md §3–§6, §14).

`run()` consumes two sources on one loop: GPT-Live server events (through the
LiveControl interface) and control requests from the app (the End button, a
lost WebRTC connection, mute changes, and a periodic tick). The voice interviewer
delegates whenever it needs a question; the conductor then closes and saves the
previous answer, asks the question writer, and hands the question back as commentary.
When the candidate goes quiet and the interviewer doesn't take its turn, the tick
points that out to it (research.md §7).
Endings run the goodbye → quiet wait → close sequence, then the evaluator.

Everything the browser hears about goes through `session.notify`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from src import config
from src.api.session_manager import ConversationSession
from src.evaluation.evaluator import EvaluationFailedError, run_evaluation
from src.evaluation.report import save_report
from src.interview import prompts
from src.interview.intents import ends_with_done, is_stop_request
from src.interview.questions import QuestionResult, QuestionUnavailableError, is_duplicate, write_question
from src.interview.record import (
    InterviewRecord,
    TranscriptFragment,
    close_answer,
    question_entry,
    record_from_interview,
    save_record,
)
from src.interview.state import InterviewQuestion, InterviewStage, ReportStatus
from src.live.events import (
    CommentaryAppended,
    DelegationCreated,
    LiveError,
    SessionClosed,
    SessionStarted,
    TranscriptDelta,
    session_close,
)

logger = logging.getLogger(__name__)

# Patched in tests.
clock = time.monotonic
TICK_SECONDS = 0.25
QUIET_SECONDS = 1.5           # goodbye finished when the interviewer is quiet this long
CLOSE_CAP_SECONDS = 10.0      # never wait longer than this for the goodbye, or for session.closed
CHECK_IN_GAP_SECONDS = 5.0    # interviewer speech after this much quiet counts as a check-in
DONE_QUIET_SECONDS = 1.0      # after "that's it" / "pronto", this much quiet ends the answer

LOST_MESSAGE = (
    "The connection to the interviewer was lost. Your saved answers are kept, "
    "and your feedback is being prepared."
)
QUESTION_UNAVAILABLE_MESSAGE = "The next question couldn't be prepared. Try answering again in a moment."
EVALUATION_FAILED_MESSAGE = (
    "Your feedback couldn't be generated. Your questions and answers are still available to download."
)


async def send_stage(session: ConversationSession) -> None:
    interview = session.interview
    await session.notify({
        "type": "interview_stage",
        "stage": interview.stage.value,
        "interview_type": interview.interview_type,
        "language": interview.language,
        "role": interview.role,
        "seniority": interview.seniority,
        "interview_id": interview.interview_id,
        "end_reason": interview.end_reason,
    })


@dataclass
class _PendingQuestion:
    result: QuestionResult
    delegation_id: str
    retried: bool = False


class InterviewRun:
    """The state of one running interview. Lives on `session.run`."""

    def __init__(self, session: ConversationSession, control) -> None:
        self.session = session
        self.control = control
        self.interview = session.interview
        self.fragments: list[TranscriptFragment] = []
        self.record: InterviewRecord = record_from_interview(self.interview, session.documents)
        self.pending: dict[str, _PendingQuestion] = {}
        self.greeted = False
        self.finished = False
        self.last_output_at = 0.0
        self.last_user_at = 0.0
        self.muted = False
        # Since the question was asked (or since the greeting): has the candidate spoken, did their
        # last words say they're done, and has the interviewer been nudged since they last spoke?
        self.user_spoke = False
        self.said_done = False
        self.nudged = False
        self.closing_since: float | None = None
        self.close_sent_at: float | None = None
        self.output_since_closing = False
        self.writer_task: asyncio.Task | None = None
        self.prefetch_task: asyncio.Task | None = None
        self.evaluation_task: asyncio.Task | None = None

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def main(self) -> None:
        self.interview.last_speech_at = clock()
        save_record(self.record)  # the transcript is downloadable from the start (FR-020)
        ticker = asyncio.create_task(self._tick())
        events = self.control.events().__aiter__()
        event_task: asyncio.Task | None = None
        request_task: asyncio.Task | None = None
        try:
            while not self.finished:
                if event_task is None:
                    event_task = asyncio.ensure_future(events.__anext__())
                if request_task is None:
                    request_task = asyncio.ensure_future(self.session.requests.get())
                done, _ = await asyncio.wait({event_task, request_task}, return_when=asyncio.FIRST_COMPLETED)
                if request_task in done:
                    request = request_task.result()
                    request_task = None
                    await self._on_request(request)
                if event_task in done and not self.finished:
                    try:
                        event = event_task.result()
                    except StopAsyncIteration:
                        event = SessionClosed(reason="close_requested" if self.close_sent_at else "connection_lost")
                    event_task = None
                    await self._on_event(event)
        finally:
            ticker.cancel()
            for task in (event_task, request_task):
                if task is not None and not task.done():
                    task.cancel()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            self.session.requests.put_nowait(("tick", None))

    # ── Requests from the app ─────────────────────────────────────────────────

    async def _on_request(self, request: tuple) -> None:
        kind, arg = request
        if kind == "end":
            if arg == "connection_lost":
                await self._connection_lost()
            elif self.interview.is_active:
                await self.begin_end(arg)
        elif kind == "mute":
            self.muted = bool(arg)
        elif kind == "tick":
            await self._on_tick()

    async def _on_tick(self) -> None:
        now = clock()
        if self.interview.is_active:
            if now - self.interview.last_speech_at >= config.INACTIVITY_END_SECONDS:
                logger.info("No speech for %d s: ending the interview", config.INACTIVITY_END_SECONDS)
                await self.begin_end("inactivity")
                return
            instruction = self._answer_end_instruction(now)
            if instruction is not None:
                self.nudged = True
                logger.info("Candidate quiet for %.1f s: nudging the interviewer", now - self.last_user_at)
                await self.control.append_instructions(instruction)
            return
        if self.interview.stage != InterviewStage.CONCLUDING or self.finished:
            return
        if self.close_sent_at is None:
            quiet = now - self.last_output_at >= QUIET_SECONDS
            goodbye_done = self.output_since_closing and quiet
            if goodbye_done or now - self.closing_since >= CLOSE_CAP_SECONDS:
                self.close_sent_at = now
                await self.control.close()
        elif now - self.close_sent_at >= CLOSE_CAP_SECONDS:
            logger.warning("No session.closed after %d s; finishing anyway", CLOSE_CAP_SECONDS)
            await self.finish()

    def _answer_end_instruction(self, now: float) -> str | None:
        """
        The nudge to send when the candidate has had the last word and gone quiet, if any.

        GPT-Live has no end-of-turn setting, and it tends to wait after an answer
        indefinitely (research.md §7). One nudge per silence; the interviewer decides
        whether the answer is really over.
        """
        interview = self.interview
        if self.muted or self.nudged or not self.user_spoke or self.pending or interview.pending_delegation_id:
            return None
        if self.last_output_at >= self.last_user_at:
            return None  # the interviewer already took its turn
        quiet = now - self.last_user_at
        if interview.stage == InterviewStage.INTRODUCING:
            return prompts.READY_CHECK_INSTRUCTION if quiet >= config.ANSWER_END_SILENCE_SECONDS else None
        if self.said_done and quiet >= DONE_QUIET_SECONDS:
            return prompts.DONE_INSTRUCTION
        if quiet >= config.ANSWER_END_SILENCE_SECONDS:
            return prompts.ANSWER_END_INSTRUCTION
        return None

    # ── GPT-Live events ───────────────────────────────────────────────────────

    async def _on_event(self, event) -> None:
        if isinstance(event, SessionStarted):
            if not self.greeted and self.interview.is_active:
                self.greeted = True
                await self.control.append_instructions(prompts.GREETING_INSTRUCTION)
        elif isinstance(event, TranscriptDelta):
            await self._on_transcript(event)
        elif isinstance(event, DelegationCreated):
            await self._on_delegation(event)
        elif isinstance(event, CommentaryAppended):
            await self._on_commentary_appended(event)
        elif isinstance(event, LiveError):
            await self._on_error(event)
        elif isinstance(event, SessionClosed):
            if self.interview.stage == InterviewStage.CONCLUDING:
                await self.finish()
            elif self.interview.is_active:
                logger.warning("GPT-Live session closed unexpectedly (%s)", event.reason)
                await self._connection_lost(send_close=False)

    async def _on_transcript(self, event: TranscriptDelta) -> None:
        self.fragments.append(TranscriptFragment(event.speaker, event.text, event.start_ms, event.end_ms))
        now = clock()
        interview = self.interview
        if event.speaker == "user":
            self.last_user_at = now
            interview.last_speech_at = now
            interview.checked_in_since_user_spoke = False
            self.user_spoke = True
            self.nudged = False
            text, language = self._current_user_text(), interview.language or "en"
            self.said_done = ends_with_done(text, language)
            if interview.is_active and is_stop_request(text, language):
                await self.begin_end("user_request")
            return

        # Interviewer speech. After a quiet gap with no user speech in between, it's a
        # check-in ("Take your time."): that resets the silence timer once (FR-025).
        after_gap = now - self.last_output_at >= CHECK_IN_GAP_SECONDS and self.last_user_at < self.last_output_at
        if not interview.checked_in_since_user_spoke:
            interview.last_speech_at = now
            if after_gap:
                interview.checked_in_since_user_spoke = True
        self.last_output_at = now
        if self.closing_since is not None:
            self.output_since_closing = True

    def _current_user_text(self) -> str:
        current = self.interview.current_question
        since = current.asked_at_ms if current else 0
        return "".join(f.text for f in self.fragments if f.speaker == "user" and f.start_ms >= since)

    async def _on_delegation(self, event: DelegationCreated) -> None:
        interview = self.interview
        if not interview.is_active:
            logger.debug("Ignoring a delegation in stage %s", interview.stage.value)
            return
        if interview.stage == InterviewStage.INTRODUCING:
            interview.begin_interviewing()
            await send_stage(self.session)
        else:
            # Save the previous answer before the next question is requested (SC-012). Close the
            # window after everything received so far: transcripts can trail the delegation.
            until = max(event.offset_ms or 0, self._latest_fragment_ms() + 1)
            await self._close_current_answer(until)

        interview.pending_delegation_id = event.delegation_id
        await self.session.notify({"type": "delegation_pending", "pending": True})
        if self.writer_task is not None and not self.writer_task.done():
            self.writer_task.cancel()
        self.writer_task = asyncio.create_task(self._deliver(event.delegation_id))

    async def _deliver(self, delegation_id: str) -> None:
        try:
            result = await self._next_question()
        except QuestionUnavailableError:
            await self._question_unavailable()
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Question writing failed")
            await self._question_unavailable()
            return
        if not self.interview.is_active:
            return
        command = await self.control.append_commentary(
            delegation_id, prompts.COMMENTARY_TEMPLATE.format(question=result.text)
        )
        self.pending[command["event_id"]] = _PendingQuestion(result, delegation_id)

    async def _next_question(self) -> QuestionResult:
        """The next question: HR's prefetched one when it's ready and still new, else a fresh one."""
        task, self.prefetch_task = self.prefetch_task, None
        if task is not None:
            try:
                result = await task
                if not is_duplicate(result.text, [q.text for q in self.interview.questions]):
                    return result
            except Exception:
                logger.info("HR prefetch failed; writing the question now")
        return await write_question(self.interview, self.session.documents)

    async def _question_unavailable(self) -> None:
        self.interview.pending_delegation_id = None
        await self.session.notify({"type": "error", "code": "QUESTION_UNAVAILABLE", "message": QUESTION_UNAVAILABLE_MESSAGE})
        await self.session.notify({"type": "delegation_pending", "pending": False})
        if self.interview.is_active:
            await self.control.append_instructions(prompts.QUESTION_UNAVAILABLE_INSTRUCTION)

    async def _on_commentary_appended(self, event: CommentaryAppended) -> None:
        pending = self.pending.pop(event.client_event_id or "", None)
        if pending is None or not self.interview.is_active:
            return
        interview = self.interview
        result = pending.result
        question = InterviewQuestion(
            index=len(interview.questions) + 1,
            text=result.text,
            asked_at_ms=event.start_ms,
            is_follow_up=result.is_follow_up,
            grounded_chunk_ids=list(result.grounded_chunk_ids),
        )
        interview.questions.append(question)
        interview.used_chunk_ids.update(result.grounded_chunk_ids)
        interview.pending_delegation_id = None
        self.user_spoke = self.said_done = self.nudged = False
        logger.info("Question %d asked", question.index)
        # No question wording goes to the browser: the live screen never shows it (003 FR-010).
        await self.session.notify({"type": "question_asked", "index": question.index, "is_follow_up": question.is_follow_up})
        await self.session.notify({"type": "delegation_pending", "pending": False})

        if interview.interview_type == "hr":
            # HR questions never depend on the answer, so write the next one now.
            self.prefetch_task = asyncio.create_task(write_question(interview, self.session.documents))

    async def _on_error(self, event: LiveError) -> None:
        pending = self.pending.pop(event.client_event_id or "", None)
        if pending is None:
            # A command error doesn't end the session (research.md §6).
            logger.warning("GPT-Live error: %s", event.code)
            return
        if pending.retried or not self.interview.is_active:
            logger.warning("Question delivery failed twice: %s", event.code)
            await self._question_unavailable()
            return
        command = await self.control.append_commentary(
            pending.delegation_id, prompts.COMMENTARY_TEMPLATE.format(question=pending.result.text)
        )
        pending.retried = True
        self.pending[command["event_id"]] = pending

    # ── Answers and the record ────────────────────────────────────────────────

    def _latest_fragment_ms(self) -> int:
        return max((f.end_ms for f in self.fragments), default=0)

    async def _close_current_answer(self, until_ms: float) -> None:
        question = self.interview.current_question
        if question is None or question.answer_text is not None:
            return
        question.answer_text, question.spoken_text = close_answer(question, self.fragments, until_ms)
        question.answered_at = datetime.now(timezone.utc)
        self.record.questions.append(question_entry(question))
        save_record(self.record)
        await self.session.notify({"type": "answer_saved", "index": question.index})

    # ── Ending ────────────────────────────────────────────────────────────────

    def _stop_question_work(self) -> None:
        for task in (self.writer_task, self.prefetch_task):
            if task is not None and not task.done():
                task.cancel()
        self.prefetch_task = None

    async def begin_end(self, reason: str) -> None:
        """Goodbye → quiet wait → session.close; finish() follows on session.closed."""
        self.interview.request_end(reason)
        self._stop_question_work()
        await send_stage(self.session)
        self.closing_since = clock()
        instruction = prompts.INACTIVITY_INSTRUCTION if reason == "inactivity" else prompts.CONCLUDE_INSTRUCTION
        await self.control.append_instructions(instruction)

    async def _connection_lost(self, send_close: bool = True) -> None:
        if not self.interview.is_active:
            return
        await self.session.notify({"type": "error", "code": "LIVE_SESSION_LOST", "message": LOST_MESSAGE})
        self.interview.request_end("connection_lost")
        self._stop_question_work()
        await send_stage(self.session)
        if send_close:
            # The browser lost the call; make sure the billed session ends too.
            try:
                await self.control.send(session_close())
            except Exception:
                pass
        await self.finish()

    async def finish(self, evaluate: bool = True) -> None:
        if self.finished:
            return
        self.finished = True
        self._stop_question_work()
        await self._close_current_answer(float("inf"))
        interview = self.interview
        self.record.ended_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self.record.end_reason = interview.end_reason
        if interview.stage == InterviewStage.CONCLUDING:
            interview.finish()
        save_record(self.record)
        await send_stage(self.session)
        if evaluate and interview.end_reason != "page_closed":
            await self._start_evaluation()

    # ── Evaluation ────────────────────────────────────────────────────────────

    async def _start_evaluation(self) -> None:
        record = self.record
        if not record.answered:
            await self._set_report_status(ReportStatus.SKIPPED)
            return
        await self._set_report_status(ReportStatus.PENDING)
        documents = self.session.documents
        resume_text = documents.resume.text[:config.RESUME_PROMPT_MAX_CHARS] if documents.resume else None
        passages = {
            q.index: documents.chunk_texts(q.grounded_chunk_ids)
            for q in self.interview.questions
            if q.grounded_chunk_ids
        }
        # Holds the record and passages, not the session: it outlives a closed tab.
        self.evaluation_task = asyncio.create_task(self._evaluate(resume_text, passages))

    async def _evaluate(self, resume_text: str | None, passages: dict[int, list[str]]) -> None:
        started = time.monotonic()
        logger.info("Evaluation started (%d questions)", len(self.record.questions))
        try:
            report = await run_evaluation(self.record, resume_text, passages)
            save_report(self.record, report)
            logger.info("Evaluation ready in %.1f s (grader: %s)", time.monotonic() - started, report["grader"])
        except EvaluationFailedError:
            await self._set_report_status(ReportStatus.FAILED, EVALUATION_FAILED_MESSAGE)
            return
        except Exception:
            logger.exception("Evaluation failed")
            await self._set_report_status(ReportStatus.FAILED, EVALUATION_FAILED_MESSAGE)
            return
        await self._set_report_status(ReportStatus.READY)

    async def _set_report_status(self, status: ReportStatus, message: str | None = None) -> None:
        self.interview.report_status = status
        self.record.report_status = status.value
        save_record(self.record)
        await self.session.notify({
            "type": "report_status",
            "status": status.value,
            "interview_id": self.record.interview_id,
            "message": message,
        })


async def run(session: ConversationSession, control) -> None:
    """Drive the interview until it concludes."""
    interview_run = InterviewRun(session, control)
    session.run = interview_run
    try:
        await interview_run.main()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Conductor crashed")
        if session.interview.is_active:
            await interview_run._connection_lost()
    # Keep the evaluation going after the conductor loop ends.
    if interview_run.evaluation_task is not None:
        await asyncio.shield(interview_run.evaluation_task)


async def on_page_closed(session: ConversationSession) -> None:
    """The app WebSocket closed mid-interview: keep what was saved, don't evaluate."""
    interview_run = getattr(session, "run", None)
    interview = session.interview
    if interview.is_active:
        interview.request_end("page_closed")
    if interview_run is not None:
        await interview_run.finish(evaluate=False)
    elif interview.stage == InterviewStage.CONCLUDING:
        interview.finish()
