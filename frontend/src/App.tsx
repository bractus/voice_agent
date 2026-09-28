import { useCallback, useEffect, useState } from 'react'
import { useVoiceSession } from './hooks/useVoiceSession'
import { Fairy, type FairyMood } from './components/Fairy'
import { TopBar, type SignalLevel } from './components/TopBar'
import { MicPermission } from './components/MicPermission'
import { SetupScreen } from './components/SetupScreen'
import { EndInterviewButton } from './components/EndInterviewButton'
import { MuteButton } from './components/MuteButton'
import { ReportPanel } from './components/ReportPanel'
import { DownloadIcon } from './components/icons'
import { STRINGS, formatClock } from './i18n'
import type { InterviewLanguage } from './services/liveApi'
import { transcriptUrl } from './services/interviewsApi'

/** Seconds since `startedAt`, ticking once a second until `endedAt`. */
function useSessionClock(startedAt: string | null, endedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!startedAt || endedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [startedAt, endedAt])
  if (!startedAt) return 0
  return ((endedAt ?? now) - new Date(startedAt).getTime()) / 1000
}

export default function App() {
  const {
    connected,
    sessionId,
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
    errorMessage,
    activity,
    live,
    connect,
    startInterview,
    endInterview,
  } = useVoiceSession()

  // The language chosen on the setup screen drives the interface until the interview
  // fixes its own (PRODUCT.md: the interface follows the interview language).
  const [setupLanguage, setSetupLanguage] = useState<InterviewLanguage>('en')
  const uiLanguage: InterviewLanguage = stage === 'setup' ? setupLanguage : language ?? setupLanguage
  const t = STRINGS[uiLanguage]

  useEffect(() => {
    document.documentElement.lang = uiLanguage
    document.title = t.appName
  }, [uiLanguage, t])

  // Where the fairy hovers: beside the wordmark, then the sky, then back home beside the wordmark.
  const [fairyAnchor, setFairyAnchor] = useState<HTMLElement | null>(null)
  const attachAnchor = useCallback((el: HTMLElement | null) => {
    if (el) setFairyAnchor(el)
  }, [])

  useEffect(() => {
    connect()
  }, [connect])

  const clock = useSessionClock(startedAt, endedAt)
  const inSetup = stage === 'setup'
  const active = stage === 'introducing' || stage === 'interviewing'
  const concluded = stage === 'concluded'

  const mood: FairyMood = !connected && !concluded
    ? 'sleeping'
    : active && live.muted
    ? 'muted'
    : pendingQuestion || (concluded && reportStatus === 'pending')
    ? 'thinking'
    : activity === 'interviewer'
    ? 'speaking'
    : activity === 'candidate'
    ? 'listening'
    : concluded
    ? 'resting'
    : 'idle'

  // Who is speaking, as a lamp that brightens (no status box).
  const signal: { level: SignalLevel; text: string } = !connected && !concluded
    ? { level: 'wait', text: t.connecting }
    : inSetup
    ? { level: 'idle', text: t.ready }
    : stage === 'concluding'
    ? { level: 'wait', text: t.wrappingUp }
    : concluded
    ? { level: 'idle', text: t.complete }
    : live.muted
    ? { level: 'idle', text: t.muted }
    : activity === 'interviewer'
    ? { level: 'active', text: t.interviewerSpeaking }
    : activity === 'candidate'
    ? { level: 'active', text: t.listening }
    : { level: 'live', text: t.live }

  const typeName = interviewType === 'technical' ? t.techLabel : interviewType === 'hr' ? t.hrLabel : null

  // State only, never question wording: the candidate listens, as in a real interview (003 FR-010).
  const caption = (() => {
    if (stage === 'concluding') return t.wrappingUp
    if (live.muted) return t.muted
    if (pendingQuestion) return t.preparingQuestion
    if (activity === 'interviewer') return t.interviewerSpeaking
    if (activity === 'candidate') return t.listening
    if (questionCount === 0) return stage === 'introducing' ? t.introducing : t.sayReady
    return t.live
  })()

  return (
    <div className="app">
      <TopBar
        t={t}
        perchRef={inSetup || concluded ? attachAnchor : undefined}
        center={
          !inSetup && typeName ? (
            <span>
              {typeName} · {t.levelFor(t[seniority ?? 'mid'], role)} · {uiLanguage === 'pt-BR' ? 'PT-BR' : 'EN'}
            </span>
          ) : null
        }
        signal={signal}
        compact={!inSetup}
      >
        {!inSetup && (
          <>
            <span className="readout">
              <span className="label">{t.session}</span>
              <span className="figures">{formatClock(clock)}</span>
            </span>
            {questionCount > 0 && (
              <span className="readout">
                <span className="label">{t.entry}</span>
                <span className="figures">{String(questionCount).padStart(2, '0')}</span>
              </span>
            )}
          </>
        )}
      </TopBar>

      {inSetup && (
        <SetupScreen
          t={t}
          sessionId={sessionId}
          canStart={connected}
          language={setupLanguage}
          onLanguageChange={setSetupLanguage}
          onStart={startInterview}
        />
      )}

      {(active || stage === 'concluding') && (
        <main className="sky">
          <div className="sky-inner">
            {/* The fairy is drawn by <Fairy/>; this is where she hovers. Just talk: nothing to hold. */}
            <div ref={attachAnchor} className="sky-stage" data-fairy-scale="1" aria-hidden="true" />
            {/* The log entry being written: its index in the margin, its state beside it (no wording). */}
            <div className="caption" aria-live="polite">
              <span className="caption-index" aria-hidden="true">
                {questionCount > 0 ? String(questionCount).padStart(2, '0') : '··'}
              </span>
              <p key={caption} className="caption-state">{caption}</p>
            </div>
          </div>
        </main>
      )}

      {active && (
        <footer className="controls">
          {/* End sits alone, well away from the other controls. */}
          <EndInterviewButton t={t} onEnd={endInterview} />
          <div className="controls-group">
            {answersSaved > 0 && interviewId && (
              <a className="btn btn-quiet" href={transcriptUrl(interviewId)} download aria-label={t.downloadTranscript}>
                <DownloadIcon />
                <span className="btn-text-optional">{t.downloadTranscript}</span>
              </a>
            )}
            <MuteButton t={t} muted={live.muted} onToggle={() => live.setMuted(!live.muted)} />
          </div>
        </footer>
      )}

      {concluded && interviewId && (
        <ReportPanel
            t={t}
            interviewId={interviewId}
            status={reportStatus}
            language={language ?? uiLanguage}
            interviewType={interviewType}
            role={role}
            seniority={seniority}
            endReason={endReason}
            startedAt={startedAt}
            onNewInterview={() => window.location.reload()}
          />
      )}

      <Fairy anchor={fairyAnchor} mood={mood} speechAnalyser={live.remoteAnalyser} micAnalyser={live.micAnalyser} />

      {errorMessage && (
        <div className="toast" role="alert">
          {errorMessage}
        </div>
      )}

      {live.permissionDenied && <MicPermission t={t} />}
    </div>
  )
}
