/**
 * Documents HTTP API client — see specs/001-mock-interview-agent/contracts/documents-api.md.
 */

export type DocumentKind = 'resume' | 'reference'

export interface UploadedDocument {
  document_id: string
  kind: DocumentKind
  filename: string
  format: string
  size_bytes: number
  chunk_count: number
  truncated: boolean
}

/** Role and seniority read from a resume (003); only on resume uploads, null when unclear. */
export interface ResumeSuggestion {
  role: string | null
  seniority: 'junior' | 'mid' | 'senior' | null
}

export interface UploadResult extends UploadedDocument {
  reference_bytes_total: number
  reference_count: number
  suggestion?: ResumeSuggestion | null
}

export interface DocumentListing {
  resume: Pick<UploadedDocument, 'document_id' | 'filename' | 'format' | 'size_bytes'> | null
  references: Omit<UploadedDocument, 'kind'>[]
  reference_bytes_total: number
  limits: {
    reference_max_files: number
    reference_max_bytes: number
    resume_max_bytes: number
  }
}

/** An error response from the API; `message` is written for the user. */
export class DocumentApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
  }
}

function documentsUrl(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/documents`
}

async function parseError(res: Response): Promise<DocumentApiError> {
  try {
    const body = (await res.json()) as { code?: string; message?: string }
    return new DocumentApiError(res.status, body.code ?? 'UNKNOWN', body.message ?? res.statusText)
  } catch {
    return new DocumentApiError(res.status, 'UNKNOWN', `Upload failed (${res.status}).`)
  }
}

export async function uploadDocument(
  sessionId: string,
  kind: DocumentKind,
  file: File,
): Promise<UploadResult> {
  const form = new FormData()
  form.append('kind', kind)
  form.append('file', file)

  let res: Response
  try {
    res = await fetch(documentsUrl(sessionId), { method: 'POST', body: form })
  } catch {
    throw new DocumentApiError(0, 'NETWORK_ERROR', `Couldn't reach the server to upload ${file.name}.`)
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as UploadResult
}

export async function listDocuments(sessionId: string): Promise<DocumentListing> {
  const res = await fetch(documentsUrl(sessionId))
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as DocumentListing
}
