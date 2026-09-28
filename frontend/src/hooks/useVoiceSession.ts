/**
 * The interview session as the UI sees it: the app WebSocket (session lifetime
 * and control frames) plus the GPT-Live WebRTC session (useLiveSession).
 *
 * Frames: specs/002-gpt-live-interview/contracts/websocket-protocol.md.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { WsClient } from '../services/wsClient'
import type { InterviewLanguage, InterviewType, Seniority } from '../services/liveApi'
import { useLiveSession, type LiveSession } from './useLiveSession'

export type { InterviewLanguage, InterviewType, Seniority } from '../services/liveApi'

export type InterviewStage = 'setup' | 'introducing' | 'interviewing' | 'concluding' | 'concluded'
export type EndReason = 'user_request' | 'end_button' | 'inactivity' | 'connection_lost' | 'page_closed'
export type ReportStatus = 'none' | 'pending' | 'ready' | 'failed' | 'skipped'

/** Who is talking right now, from live audio levels. */
export type VoiceActivity = 'quiet' | 'interviewer' | 'candidate'

export const LAST_INTERVIEW_KEY = 'voice_last_interview_id'

interface UseVoiceSessionResult {
  connected: boolean
  sessionId: string
  stage: InterviewStage
  interviewType: InterviewType | null
  language: InterviewLanguage | null
  role: string | null
  seniority: Seniority | null
  interviewId: string | null
  endReason: EndReason | null
  questionCount: number
  /** When the interview left setup (ISO), for the session clock and the report header. */
  startedAt: string | null
  /** When it concluded, so the clock stops. */
  endedAt: number | null
  answersSaved: number
  pendingQuestion: boolean
  reportStatus: ReportStatus
  reportMessage: string | null
  errorMessage: string
  activity: VoiceActivity
  live: LiveSession
  connect: () => void
  startInterview: (
    type: InterviewType,
    language: InterviewLanguage,
    role: string | null,
    seniority: Seniority,
  ) => Promise<void>
  endInterview: () => void
}

export function getSessionId(): string {
  let id = sessionStorage.getItem('voice_session_id')
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem('voice_session_id', id)
  }
  return id
}

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/${getSessionId()}`
}

function rememberInterview(id: string): void {
  try {
    localStorage.setItem(LAST_INTERVIEW_KEY, id)
  } catch {
    /* storage unavailable: the "Last interview" row just won't show */
  }
}

// RMS thresholds for "someone is speaking", and how long a level must hold.
const REMOTE_THRESHOLD = 0.02
const MIC_THRESHOLD = 0.015
const HOLD_MS = 250

function rms(analyser: AnalyserNode, buf: Float32Array<ArrayBuffer>): number {
  analyser.getFloatTimeDomainData(buf)
  let sum = 0
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
  return Math.sqrt(sum / buf.length)
}

/**
 * Who's speaking, from the two analysers. Sampled every animation frame but only
 * sets React state when the answer changes, so it never re-renders per frame.
 */
function useVoiceActivity(remote: AnalyserNode | null, mic: AnalyserNode | null, micMuted: boolean): VoiceActivity {
  const [activity, setActivity] = useState<VoiceActivity>('quiet')
  const mutedRef = useRef(micMuted)
  mutedRef.current = micMuted

  useEffect(() => {
    if (!remote && !mic) {
      setActivity('quiet')
      return
    }
    const remoteBuf = remote ? new Float32Array(remote.fftSize) : null
    const micBuf = mic ? new Float32Array(mic.fftSize) : null
    let lastRemote = 0
    let lastMic = 0
    let current: VoiceActivity = 'quiet'
    let raf = 0
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick)
      if (remote && remoteBuf && rms(remote, remoteBuf) > REMOTE_THRESHOLD) lastRemote = now
      if (mic && micBuf && !mutedRef.current && rms(mic, micBuf) > MIC_THRESHOLD) lastMic = now
      const next: VoiceActivity =
        now - lastRemote < HOLD_MS ? 'interviewer' : now - lastMic < HOLD_MS ? 'candidate' : 'quiet'
      if (next !== current) {
        current = next
        setActivity(next)
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [remote, mic])

  return activity
}

export function useVoiceSession(): UseVoiceSessionResult {
  const [connected, setConnected] = useState(false)
  const [stage, setStage] = useState<InterviewStage>('setup')
  const [interviewType, setInterviewType] = useState<InterviewType | null>(null)
  const [language, setLanguage] = useState<InterviewLanguage | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [seniority, setSeniority] = useState<Seniority | null>(null)
  const [interviewId, setInterviewId] = useState<string | null>(null)
  const [endReason, setEndReason] = useState<EndReason | null>(null)
  const [questionCount, setQuestionCount] = useState(0)
  const [startedAt, setStartedAt] = useState<string | null>(null)
  const [endedAt, setEndedAt] = useState<number | null>(null)
  const [answersSaved, setAnswersSaved] = useState(0)
  const [pendingQuestion, setPendingQuestion] = useState(false)
  const [reportStatus, setReportStatus] = useState<ReportStatus>('none')
  const [reportMessage, setReportMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const clientRef = useRef<WsClient | null>(null)
  const stageRef = useRef<InterviewStage>('setup')
  const live = useLiveSession()
  const { sendEvent, close: closeLive, start: startLive, setEventHandler, setDisconnectHandler } = live
  const activity = useVoiceActivity(live.remoteAnalyser, live.micAnalyser, live.muted)

  const send = useCallback((payload: object) => {
    clientRef.current?.send(JSON.stringify(payload))
  }, [])

  // Browser-relay fallback: forward data-channel events; harmless when the server uses a sideband.
  useEffect(() => {
    setEventHandler((event) => {
      if (stageRef.current !== 'setup') send({ type: 'live_event', event })
    })
    setDisconnectHandler(() => {
      const current = stageRef.current
      if (current === 'introducing' || current === 'interviewing') send({ type: 'live_disconnected' })
    })
    return () => {
      setEventHandler(null)
      setDisconnectHandler(null)
    }
  }, [setEventHandler, setDisconnectHandler, send])

  // The server nudges the interviewer when the candidate goes quiet; muted silence is intentional.
  useEffect(() => {
    const current = stageRef.current
    if (current === 'introducing' || current === 'interviewing') send({ type: 'mic_muted', muted: live.muted })
  }, [live.muted, send])

  const connect = useCallback(() => {
    if (clientRef.current) return
    const client = new WsClient()
    clientRef.current = client

    client.onConnectionState = (isConnected) => setConnected(isConnected)

    client.onTextFrame = (msg) => {
      switch (msg.type) {
        case 'interview_stage': {
          const next = msg.stage as InterviewStage
          if (stageRef.current === 'setup' && next !== 'setup') setStartedAt(new Date().toISOString())
          if (next === 'concluded') setEndedAt((prev) => prev ?? Date.now())
          stageRef.current = next
          setStage(next)
          setInterviewType((msg.interview_type as InterviewType | null) ?? null)
          setLanguage((msg.language as InterviewLanguage | null) ?? null)
          setRole((msg.role as string | null) ?? null)
          setSeniority((msg.seniority as Seniority | null) ?? null)
          setEndReason((msg.end_reason as EndReason | null) ?? null)
          const id = (msg.interview_id as string | null) ?? null
          setInterviewId(id)
          if (id) rememberInterview(id)
          break
        }
        case 'delegation_pending':
          setPendingQuestion(Boolean(msg.pending))
          break
        case 'question_asked':
          setQuestionCount(msg.index as number)
          break
        case 'answer_saved':
          setAnswersSaved(msg.index as number)
          break
        case 'report_status':
          setReportStatus(msg.status as ReportStatus)
          setReportMessage((msg.message as string | null) ?? null)
          break
        case 'live_command':
          sendEvent(msg.event as Record<string, unknown>)
          break
        case 'error':
          setErrorMessage(msg.message as string)
          break
      }
    }

    client.connect(getWsUrl(), getSessionId())
  }, [sendEvent])

  // The call is over once the interview concludes.
  useEffect(() => {
    if (stage === 'concluded') closeLive()
  }, [stage, closeLive])

  const startInterview = useCallback(
    async (type: InterviewType, lang: InterviewLanguage, jobRole: string | null, level: Seniority) => {
      setErrorMessage('')
      try {
        await startLive(getSessionId(), type, lang, jobRole, level)
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : 'The interviewer couldn\'t be started.')
      }
    },
    [startLive],
  )

  const endInterview = useCallback(() => send({ type: 'end_interview' }), [send])

  useEffect(() => {
    return () => {
      clientRef.current?.disconnect()
      clientRef.current = null
    }
  }, [])

  return {
    connected,
    sessionId: getSessionId(),
    stage,
    interviewType,
    language,
    role,
    seniority,
    interviewId,
    endReason,
    questionCount,
    startedAt,
    endedAt,
    answersSaved,
    pendingQuestion,
    reportStatus,
    reportMessage,
    errorMessage,
    activity,
    live,
    connect,
    startInterview,
    endInterview,
  }
}
