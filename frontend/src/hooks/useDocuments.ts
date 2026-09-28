/**
 * Upload state for the setup screen: the resume, the reference files, and
 * any per-file error messages returned by the documents API.
 */
import { useCallback, useState } from 'react'
import {
  DocumentApiError,
  listDocuments,
  uploadDocument,
  type DocumentKind,
  type ResumeSuggestion,
  type UploadedDocument,
} from '../services/documentsApi'

export interface UploadError {
  kind: DocumentKind
  filename: string
  message: string
}

interface UseDocumentsResult {
  resume: UploadedDocument | null
  references: UploadedDocument[]
  referenceBytesTotal: number
  uploading: string[]
  errors: UploadError[]
  /** The latest resume upload's suggestion; `seq` changes on every resume upload. */
  resumeSuggestion: { value: ResumeSuggestion; seq: number } | null
  upload: (kind: DocumentKind, files: File[]) => Promise<void>
  refresh: () => Promise<number>
  clearErrors: () => void
}

export function useDocuments(sessionId: string): UseDocumentsResult {
  const [resume, setResume] = useState<UploadedDocument | null>(null)
  const [references, setReferences] = useState<UploadedDocument[]>([])
  const [referenceBytesTotal, setReferenceBytesTotal] = useState(0)
  const [uploading, setUploading] = useState<string[]>([])
  const [errors, setErrors] = useState<UploadError[]>([])
  const [resumeSuggestion, setResumeSuggestion] = useState<{ value: ResumeSuggestion; seq: number } | null>(null)

  const upload = useCallback(
    async (kind: DocumentKind, files: File[]) => {
      setErrors((prev) => prev.filter((e) => e.kind !== kind))
      // One file at a time, so the server checks limits against what's already accepted.
      for (const file of files) {
        setUploading((prev) => [...prev, file.name])
        try {
          const result = await uploadDocument(sessionId, kind, file)
          if (kind === 'resume') {
            setResume(result)
            if (result.suggestion) {
              const value = result.suggestion
              setResumeSuggestion((prev) => ({ value, seq: (prev?.seq ?? 0) + 1 }))
            }
          } else {
            setReferences((prev) => [...prev, result])
            setReferenceBytesTotal(result.reference_bytes_total)
          }
        } catch (e) {
          const message =
            e instanceof DocumentApiError ? e.message : `${file.name} could not be uploaded.`
          setErrors((prev) => [...prev, { kind, filename: file.name, message }])
        } finally {
          setUploading((prev) => {
            const i = prev.indexOf(file.name)
            return i === -1 ? prev : [...prev.slice(0, i), ...prev.slice(i + 1)]
          })
        }
      }
    },
    [sessionId],
  )

  /** Reload from the server. Returns how many files the server still holds. */
  const refresh = useCallback(async () => {
    try {
      const listing = await listDocuments(sessionId)
      setResume(listing.resume ? { ...listing.resume, kind: 'resume', chunk_count: 0, truncated: false } : null)
      setReferences(listing.references.map((r) => ({ ...r, kind: 'reference' as const })))
      setReferenceBytesTotal(listing.reference_bytes_total)
      return (listing.resume ? 1 : 0) + listing.references.length
    } catch {
      return 0
    }
  }, [sessionId])

  const clearErrors = useCallback(() => setErrors([]), [])

  return { resume, references, referenceBytesTotal, uploading, errors, resumeSuggestion, upload, refresh, clearErrors }
}
