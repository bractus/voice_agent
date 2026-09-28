import { useEffect, useRef, useState, type ChangeEvent } from 'react'

const STEP_IDS = ['plan-interview', 'plan-material', 'plan-start'] as const

/** The plan section currently in view, for the rail's current-step state. */
function useCurrentStep(): string {
  const [current, setCurrent] = useState<string>(STEP_IDS[0])
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setCurrent(visible[0].target.id)
      },
      { rootMargin: '-30% 0px -55% 0px' },
    )
    STEP_IDS.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [])
  return current
}
import { useDocuments, type UploadError } from '../hooks/useDocuments'
import { LANGUAGE_NAMES, type Strings } from '../i18n'
import type { DocumentKind } from '../services/documentsApi'
import { getStatus, type InterviewLanguage, type InterviewType, type Seniority, type StatusResult } from '../services/liveApi'
import { CheckIcon, UploadIcon } from './icons'
import { InterviewTypePicker } from './InterviewTypePicker'
import { LanguagePicker } from './LanguagePicker'
import { LastInterview } from './LastInterview'
import { SeniorityPicker } from './SeniorityPicker'

interface Props {
  t: Strings
  sessionId: string
  canStart: boolean
  language: InterviewLanguage
  onLanguageChange: (language: InterviewLanguage) => void
  /** Resolves once the interviewer has started, or failed to (the error shows elsewhere). */
  onStart: (type: InterviewType, language: InterviewLanguage, role: string | null, seniority: Seniority) => Promise<void>
}

const REFERENCE_MAX_FILES = 5

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
}

function Errors({ errors }: { errors: UploadError[] }) {
  if (errors.length === 0) return null
  return (
    <ul role="alert" style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
      {errors.map((e) => (
        <li key={`${e.filename}-${e.message}`} className="error-text">
          {e.message}
        </li>
      ))}
    </ul>
  )
}

function PickButton({
  label,
  accept,
  multiple,
  disabled,
  onFiles,
}: {
  label: string
  accept: string
  multiple?: boolean
  disabled: boolean
  onFiles: (files: File[]) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = '' // allow picking the same file again
    if (files.length) onFiles(files)
  }
  return (
    <>
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} hidden onChange={onChange} />
      <button type="button" className="btn btn-quiet" disabled={disabled} onClick={() => inputRef.current?.click()}>
        <UploadIcon />
        {label}
      </button>
    </>
  )
}

/** The observing plan: interview, material, start. Shown while the interview stage is "setup". */
export function SetupScreen({ t, sessionId, canStart, language, onLanguageChange, onStart }: Props) {
  const { resume, references, referenceBytesTotal, uploading, errors, resumeSuggestion, upload, refresh } =
    useDocuments(sessionId)
  const busy = uploading.length > 0
  const errorsFor = (kind: DocumentKind) => errors.filter((e) => e.kind === kind)
  const referencesFull = references.length >= REFERENCE_MAX_FILES
  // HR is preselected (user request, 2026-09-25); the choice can still be changed before starting.
  const [interviewType, setInterviewType] = useState<InterviewType | null>('hr')
  const [starting, setStarting] = useState(false)
  // Role and seniority (003). Mid-level is the default level.
  const [role, setRole] = useState('')
  const [seniority, setSeniority] = useState<Seniority>('mid')
  // Who set each value: a resume suggestion never overwrites the candidate's own input (003 FR-005).
  const [roleSource, setRoleSource] = useState<'default' | 'resume' | 'user'>('default')
  const [senioritySource, setSenioritySource] = useState<'default' | 'resume' | 'user'>('default')
  useEffect(() => {
    if (!resumeSuggestion) return
    const { role: suggestedRole, seniority: suggestedLevel } = resumeSuggestion.value
    if (suggestedRole && roleSource !== 'user') {
      setRole(suggestedRole)
      setRoleSource('resume')
    }
    if (suggestedLevel && senioritySource !== 'user') {
      setSeniority(suggestedLevel)
      setSenioritySource('resume')
    }
    // Only a new suggestion (seq) re-applies; the sources are read, not watched.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeSuggestion?.seq])

  // Whether the OpenAI key works (FR-018). Re-checked whenever the connection comes back.
  const [status, setStatus] = useState<StatusResult | null>(null)
  useEffect(() => {
    if (!canStart) return
    let cancelled = false
    getStatus()
      .then((s) => !cancelled && setStatus(s))
      .catch(() => !cancelled && setStatus(null))
    return () => {
      cancelled = true
    }
  }, [canStart])
  const openaiReady = status?.openai === 'ok'
  const openaiMessage = status && status.openai !== 'ok' ? t.openai[status.openai] : null

  // A dropped connection ends the server session, and its uploads with it (FR-016).
  const [lostFiles, setLostFiles] = useState(false)
  const wasConnected = useRef(canStart)
  const heldFiles = (resume ? 1 : 0) + references.length
  useEffect(() => {
    if (canStart && !wasConnected.current && heldFiles > 0) {
      refresh().then((onServer) => setLostFiles(onServer < heldFiles))
    }
    wasConnected.current = canStart
  }, [canStart, heldFiles, refresh])

  const currentStep = useCurrentStep()
  const typeName = interviewType === 'technical' ? t.techLabel : t.hrLabel
  const levelName = t.levelFor(t[seniority], role.trim() || null)
  const material = [
    resume ? t.withResume(resume.filename) : null,
    references.length ? t.withReferences(references.length) : null,
  ].filter(Boolean)

  const start = async () => {
    if (!interviewType) return
    setStarting(true)
    await onStart(interviewType, language, role.trim() || null, seniority)
    setStarting(false)
  }

  return (
    <main className="plan">
      <aside className="plan-rail">
        <nav aria-label={t.planTitle}>
          <ol className="steps">
            {([
              ['plan-interview', '01', t.stepInterview],
              ['plan-material', '02', t.stepMaterial],
              ['plan-start', '03', t.stepStart],
            ] as const).map(([id, number, label]) => (
              <li key={id}>
                <a href={`#${id}`} aria-current={currentStep === id ? 'step' : undefined}>
                  <span className="step-number">{number}</span>
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <LastInterview t={t} language={language} />
      </aside>

      <div className="plan-body">
        <header className="plan-head">
          <h1>{t.planTitle}</h1>
          <p>{t.planIntro}</p>
        </header>

        <section id="plan-interview" className="plan-section" aria-labelledby="plan-interview-title">
          <div>
            <h2 id="plan-interview-title"><span className="section-number">01</span>{t.stepInterview}</h2>
            <div className="section-body">
              {/* Language first: it decides the language of everything that follows (003 FR-003). */}
              <div className="field">
                <span className="label">{t.languageLabel}</span>
                <LanguagePicker t={t} value={language} onChange={onLanguageChange} disabled={starting} />
                <p className="field-hint">{t.languageHint}</p>
              </div>
              <div className="field">
                <span className="label">{t.typeLabel}</span>
                <InterviewTypePicker t={t} value={interviewType} onChange={setInterviewType} disabled={starting} />
              </div>
              <div className="field">
                <label className="label" htmlFor="plan-role">{t.roleLabel}</label>
                <div className="text-row">
                  <input
                    id="plan-role"
                    className="text-input"
                    type="text"
                    maxLength={80}
                    autoComplete="organization-title"
                    placeholder={t.rolePlaceholder}
                    value={role}
                    disabled={starting}
                    onChange={(e) => {
                      setRole(e.target.value)
                      setRoleSource('user')
                    }}
                    aria-describedby="plan-role-hint"
                  />
                </div>
                {roleSource === 'resume' && <p className="field-suggested">{t.suggestedFromResume}</p>}
                <p id="plan-role-hint" className="field-hint">{t.roleHint}</p>
              </div>
              <div className="field">
                <span className="label">{t.seniorityLabel}</span>
                <SeniorityPicker
                  t={t}
                  value={seniority}
                  onChange={(value) => {
                    setSeniority(value)
                    setSenioritySource('user')
                  }}
                  disabled={starting}
                />
                {senioritySource === 'resume' && <p className="field-suggested">{t.suggestedFromResume}</p>}
              </div>
            </div>
          </div>
        </section>

        <section id="plan-material" className="plan-section" aria-labelledby="plan-material-title">
          <div>
            <h2 id="plan-material-title"><span className="section-number">02</span>{t.stepMaterial}</h2>
            <div className="section-body">
              <div className="field">
                <div className="field-head">
                  <span className="label">{t.resumeLabel}</span>
                  <span className="label">{t.optional}</span>
                </div>
                <ul className="file-list">
                  <li className="file-row">
                    {resume ? (
                      <span className="file-name">
                        <CheckIcon />
                        <span>{resume.filename}</span>
                        <span className="file-meta figures">{formatSize(resume.size_bytes)}</span>
                      </span>
                    ) : (
                      <span className="file-empty">{t.noResume}</span>
                    )}
                    <PickButton
                      label={resume ? t.replace : t.upload}
                      accept=".pdf,.docx,.txt,.md"
                      disabled={!canStart || busy || starting}
                      onFiles={(files) => upload('resume', files.slice(0, 1))}
                    />
                  </li>
                </ul>
                <p className="field-hint">{t.resumeHint}</p>
                <Errors errors={errorsFor('resume')} />
              </div>

              <div className="field">
                <div className="field-head">
                  <span className="label">{t.referencesLabel}</span>
                  <span className="label figures">
                    {references.length > 0
                      ? `${t.filesOf(references.length, REFERENCE_MAX_FILES)} · ${formatSize(referenceBytesTotal)} / 20 MB`
                      : t.optional}
                  </span>
                </div>
                <ul className="file-list">
                  {references.map((r) => (
                    <li key={r.document_id} className="file-row">
                      <span className="file-name">
                        <CheckIcon />
                        <span>{r.filename}</span>
                        <span className="file-meta figures">{formatSize(r.size_bytes)}</span>
                      </span>
                      {r.truncated && <span className="file-warn">{t.truncated}</span>}
                    </li>
                  ))}
                  <li className="file-row">
                    <span className="file-empty">{references.length === 0 ? t.noReferences : ''}</span>
                    <PickButton
                      label={t.addFiles}
                      accept=".pdf,.txt,.epub,.md"
                      multiple
                      disabled={!canStart || busy || referencesFull || starting}
                      onFiles={(files) => upload('reference', files)}
                    />
                  </li>
                </ul>
                <p className="field-hint">{t.referencesHint}</p>
                <Errors errors={errorsFor('reference')} />
              </div>

              {lostFiles && <p className="error-text" role="alert">{t.lostFiles}</p>}
            </div>
          </div>
        </section>

        <section id="plan-start" className="plan-section" aria-labelledby="plan-start-title">
          <div>
            <h2 id="plan-start-title"><span className="section-number">03</span>{t.stepStart}</h2>
            <div className="section-body">
              <p className="start-summary">
                {t.summary(typeName, LANGUAGE_NAMES[language][language])} · {levelName}
                {material.length > 0 && <span className="muted"> · {material.join(' · ')}</span>}
              </p>
              <p className="privacy">{t.privacy}</p>
              {openaiMessage && <p className="error-text" role="alert">{openaiMessage}</p>}
              <div className="start-row">
                <button
                  type="button"
                  className="btn btn-primary btn-lg"
                  onClick={start}
                  disabled={!canStart || busy || !interviewType || !openaiReady || starting}
                >
                  {!canStart
                    ? t.connecting
                    : busy
                    ? t.processing(uploading[0])
                    : starting
                    ? t.starting
                    : t.start}
                </button>
                {canStart && !interviewType && <span className="muted">{t.chooseType}</span>}
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
