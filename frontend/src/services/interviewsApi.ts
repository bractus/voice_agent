/**
 * Interview files API — see specs/002-gpt-live-interview/contracts/http-api.md.
 */
import type { InterviewLanguage, InterviewType } from './liveApi'

export type ReportStatus = 'none' | 'pending' | 'ready' | 'failed' | 'skipped'

export interface InterviewSummary {
  interview_id: string
  interview_type: InterviewType
  language: InterviewLanguage
  started_at: string
  ended_at: string | null
  end_reason: string | null
  question_count: number
  report_status: ReportStatus
}

interface ReportBase {
  interview_id: string
  generated_at: string
  model: string
  language: InterviewLanguage
  interview_type: InterviewType
  role?: string | null
  seniority?: 'junior' | 'mid' | 'senior'
  questions: { index: number; text: string; answer_text: string }[]
}

/** Reports written before specs/004: a 1–5 rating and advice to improve. */
export interface ReportV1 extends ReportBase {
  format?: undefined
  per_question: { index: number; rating: number; what_worked: string; to_improve: string }[]
  overall: { summary: string; strengths: string[]; areas_to_improve: string[] }
}

export interface ModelAnswerCheck {
  passed: boolean
  score: number
  level: number
  rewritten: boolean
}

/** specs/004: the grader's 0–5 score as returned, and the exact 5/5 answer. */
export interface ReportV2 extends ReportBase {
  format: 2
  grader: 'jev' | 'writer'
  grader_model: string | null
  writer_model: string
  per_question: {
    index: number
    score: number
    level: number
    what_worked: string
    missing: string
    model_answer: string
    model_answer_check: ModelAnswerCheck | null
  }[]
  overall: { summary: string; strengths: string[]; areas_to_improve: { text: string; questions: number[] }[] }
}

export type ReportJson = ReportV1 | ReportV2

export const isReportV2 = (report: ReportJson): report is ReportV2 => report.format === 2

const base = (id: string) => `/api/interviews/${encodeURIComponent(id)}`

export const transcriptUrl = (id: string) => `${base(id)}/transcript`
export const reportUrl = (id: string) => `${base(id)}/report`

/** The summary, or null when the interview no longer exists (e.g. its folder was deleted). */
export async function getInterview(id: string): Promise<InterviewSummary | null> {
  const res = await fetch(base(id))
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getReport(id: string): Promise<ReportJson> {
  const res = await fetch(`${reportUrl(id)}?format=json`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
