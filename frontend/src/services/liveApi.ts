/**
 * Live-session HTTP API — see specs/002-gpt-live-interview/contracts/http-api.md.
 */

export type InterviewType = 'hr' | 'technical'
export type InterviewLanguage = 'en' | 'pt-BR'
export type Seniority = 'junior' | 'mid' | 'senior'
export type OpenAIStatus = 'ok' | 'missing_key' | 'invalid_key' | 'model_unavailable' | 'unavailable'

export interface StatusResult {
  openai: OpenAIStatus
  message: string | null
}

export interface LiveStartResult {
  sdp: string
  live_session_id: string
  interview_id: string
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.message === 'string') return body.message
  } catch {
    /* not JSON */
  }
  return `The interviewer couldn't be started (HTTP ${res.status}).`
}

export async function getStatus(): Promise<StatusResult> {
  const res = await fetch('/api/status')
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export async function startLive(
  sessionId: string,
  interviewType: InterviewType,
  language: InterviewLanguage,
  sdp: string,
  role: string | null = null,
  seniority: Seniority = 'mid',
): Promise<LiveStartResult> {
  const trimmedRole = role?.trim() || undefined
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/live`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interview_type: interviewType, language, role: trimmedRole, seniority, sdp }),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}
