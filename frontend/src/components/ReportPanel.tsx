import { useEffect, useState, type CSSProperties } from 'react'
import type { EndReason, ReportStatus } from '../hooks/useVoiceSession'
import { LANGUAGE_NAMES, formatDate, type Strings } from '../i18n'
import type { InterviewLanguage, InterviewType, Seniority } from '../services/liveApi'
import { getReport, isReportV2, reportUrl, transcriptUrl, type ReportJson, type ReportV1, type ReportV2 } from '../services/interviewsApi'
import { DownloadIcon } from './icons'

interface Props {
  t: Strings
  interviewId: string
  status: ReportStatus
  language: InterviewLanguage
  interviewType: InterviewType | null
  role: string | null
  seniority: Seniority | null
  endReason: EndReason | null
  startedAt: string | null
  onNewInterview: () => void
}

/**
 * The score as atlas magnitude: one disc, larger and brighter for a stronger answer.
 * Format 2 scores are the grader's, 0–5 with decimals; format 1 ratings are whole 1–5.
 */
function Magnitude({ value, text, label }: { value: number; text: string; label: string }) {
  const r = Math.min(5, Math.max(0, value))
  // 0 → a faint 3 px point; 5 → a bright 16 px disc. Weak answers read as dim specks at a glance.
  const style = { '--d': `${3 + r * 2.6}px`, '--o': `${0.2 + r * 0.16}` } as CSSProperties
  return (
    <span className="magnitude" role="img" aria-label={`${label}: ${text}`}>
      <span className="magnitude-disc" style={style} aria-hidden="true" />
      <span className="magnitude-text figures" aria-hidden="true">{text}</span>
    </span>
  )
}

/** The model answer, with every [example value] marked as a slot to replace. Never raw HTML. */
function WithSlots({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\[[^\]\n]+\])/).map((part, i) =>
        /^\[[^\]\n]+\]$/.test(part) ? <mark key={i} className="slot">{part}</mark> : part,
      )}
    </>
  )
}

type EntryV2 = ReportV2['per_question'][number]
type EntryV1 = ReportV1['per_question'][number]

function FeedbackV2({ t, fb }: { t: Strings; fb: EntryV2 }) {
  const check = fb.model_answer_check
  return (
    <>
      <div className="entry-notes">
        <p>
          <span className="label">{t.whatWorked}</span>
          {fb.what_worked}
        </p>
        <p>
          <span className="label">{t.whatWasMissing}</span>
          {fb.missing}
        </p>
      </div>
      <blockquote className="model-answer">
        <span className="label">{t.modelAnswer}</span>
        <span className="model-answer-hint">{fb.level === 5 ? t.alreadyTop : t.modelAnswerHint}</span>
        <p><WithSlots text={fb.model_answer} /></p>
      </blockquote>
      {check && !check.passed && <p className="log-note entry-check">{t.checkNote(t.formatScore(check.score))}</p>}
    </>
  )
}

function FeedbackV1({ t, fb }: { t: Strings; fb: EntryV1 }) {
  return (
    <div className="entry-notes">
      <p>
        <span className="label">{t.whatWorked}</span>
        {fb.what_worked}
      </p>
      <p>
        <span className="label">{t.toImprove}</span>
        {fb.to_improve}
      </p>
    </div>
  )
}

/** An overall area to improve: format 2 names the questions it showed in. */
function areaText(t: Strings, area: string | { text: string; questions: number[] }): string {
  if (typeof area === 'string') return area
  return area.questions.length ? `${area.text} (${t.areaQuestions(area.questions)})` : area.text
}

const pad = (n: number) => String(n).padStart(2, '0')

/** The interview log: one entry per answer, then the overall view (FR-021, FR-022). */
export function ReportPanel({ t, interviewId, status, language, interviewType, role, seniority, endReason, startedAt, onNewInterview }: Props) {
  const [report, setReport] = useState<ReportJson | null>(null)
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    if (status !== 'ready') return
    let cancelled = false
    getReport(interviewId)
      .then((r) => !cancelled && setReport(r))
      .catch(() => !cancelled && setLoadError(true))
    return () => {
      cancelled = true
    }
  }, [status, interviewId])

  const ending = endReason === 'inactivity' ? t.endedInactivity : endReason === 'connection_lost' ? t.endedConnection : null
  const type = (report?.interview_type ?? interviewType) === 'technical' ? t.techLabel : t.hrLabel
  const level = (report?.seniority ?? seniority ?? 'mid') as Seniority
  const meta = [
    type,
    t.levelFor(t[level], report?.role ?? role),
    LANGUAGE_NAMES[language][language],
    startedAt ? formatDate(startedAt, language) : null,
    report ? t.entries(report.questions.length) : null,
  ].filter(Boolean)

  return (
    <main className="log" aria-live="polite">
      <header className="log-head">
        <div>
          <h1>{t.reportTitle}</h1>
          <p className="log-meta">{meta.join(' · ')}</p>
        </div>
        <div className="log-actions">
          {status === 'ready' && (
            <a className="btn btn-primary" href={reportUrl(interviewId)} download>
              <DownloadIcon />
              {t.downloadReport}
            </a>
          )}
          <a className="btn btn-secondary" href={transcriptUrl(interviewId)} download>
            <DownloadIcon />
            {t.downloadTranscript}
          </a>
        </div>
      </header>
      {ending && <p className="log-note">{ending}</p>}
      {report && isReportV2(report) && report.grader === 'writer' && <p className="log-note">{t.fallbackGrades}</p>}

      {status === 'pending' && <p className="log-status">{t.pending}</p>}
      {status === 'skipped' && <p className="log-status">{t.skipped}</p>}
      {(status === 'failed' || loadError) && <p className="log-status error-text">{t.reportFailed}</p>}

      {report && (
        <>
          <ol className="entries">
            {report.questions.map((q) => {
              const v2 = isReportV2(report) ? report.per_question.find((p) => p.index === q.index) : undefined
              const v1 = !isReportV2(report) ? report.per_question.find((p) => p.index === q.index) : undefined
              // Guard: an entry of neither shape shows only the question and the answer.
              const fb2 = v2 && typeof v2.score === 'number' && typeof v2.model_answer === 'string' ? v2 : undefined
              const fb1 = v1 && typeof v1.rating === 'number' ? v1 : undefined
              return (
                <li key={q.index} className="entry">
                  <div className="entry-index">
                    <span className="figures" aria-label={`${t.question} ${q.index}`}>{pad(q.index)}</span>
                    {fb2 && <Magnitude value={fb2.score} text={t.formatScore(fb2.score)} label={t.rating} />}
                    {fb1 && <Magnitude value={fb1.rating} text={`${fb1.rating}/5`} label={t.rating} />}
                  </div>
                  <div className="entry-body">
                    <p className="entry-question">{q.text}</p>
                    <blockquote className="entry-answer">
                      <span className="label" style={{ display: 'block', marginBottom: 6 }}>{t.yourAnswer}</span>
                      {q.answer_text || t.noAnswer}
                    </blockquote>
                    {fb2 && <FeedbackV2 t={t} fb={fb2} />}
                    {fb1 && <FeedbackV1 t={t} fb={fb1} />}
                  </div>
                </li>
              )
            })}
          </ol>
          <section className="overall" aria-label={t.overall}>
            <span className="label">{t.overall}</span>
            <div className="overall-body">
              <p className="overall-summary">{report.overall.summary}</p>
              <div className="overall-lists">
                <div>
                  <span className="label">{t.strengths}</span>
                  <ul>
                    {report.overall.strengths.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <span className="label">{t.areasToImprove}</span>
                  <ul>
                    {report.overall.areas_to_improve.map((a) => {
                      const text = areaText(t, a)
                      return <li key={text}>{text}</li>
                    })}
                  </ul>
                </div>
              </div>
            </div>
          </section>
        </>
      )}

      <footer className="log-foot">
        <button type="button" className="btn btn-secondary" onClick={onNewInterview}>
          {t.newInterview}
        </button>
      </footer>
    </main>
  )
}
