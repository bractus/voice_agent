import { useEffect, useState } from 'react'
import { LAST_INTERVIEW_KEY } from '../hooks/useVoiceSession'
import { formatDate, type Strings } from '../i18n'
import type { InterviewLanguage } from '../services/liveApi'
import { getInterview, reportUrl, transcriptUrl, type InterviewSummary } from '../services/interviewsApi'

function readLastId(): string | null {
  try {
    return localStorage.getItem(LAST_INTERVIEW_KEY)
  } catch {
    return null
  }
}

function forget(): void {
  try {
    localStorage.removeItem(LAST_INTERVIEW_KEY)
  } catch {
    /* ignore */
  }
}

/** "Last interview": its transcript and, once ready, its report (FR-022). */
export function LastInterview({ t, language }: { t: Strings; language: InterviewLanguage }) {
  const [summary, setSummary] = useState<InterviewSummary | null>(null)

  useEffect(() => {
    const id = readLastId()
    if (!id) return
    let cancelled = false
    getInterview(id)
      .then((s) => {
        if (cancelled) return
        if (s === null) forget()
        setSummary(s)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  if (!summary) return null
  const type = summary.interview_type === 'hr' ? t.hrLabel : t.techLabel
  return (
    <section className="last-interview" aria-label={t.lastInterview}>
      <h2>{t.lastInterview}</h2>
      <p>
        {type}
        <br />
        <span className="muted">{formatDate(summary.started_at, language)}</span>
      </p>
      <span className="last-interview-links">
        <a href={transcriptUrl(summary.interview_id)} download>
          {t.transcript}
        </a>
        {summary.report_status === 'ready' ? (
          <a href={reportUrl(summary.interview_id)} download>
            {t.report}
          </a>
        ) : summary.report_status === 'pending' ? (
          <span className="muted">{t.reportNotReady}</span>
        ) : summary.report_status === 'failed' ? (
          <span className="muted">{t.reportUnavailable}</span>
        ) : null}
      </span>
    </section>
  )
}
