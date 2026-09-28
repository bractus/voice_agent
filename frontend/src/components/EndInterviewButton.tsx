import type { Strings } from '../i18n'
import { EndIcon } from './icons'

/** Ends the interview (sends end_interview). Kept apart from the other controls. */
export function EndInterviewButton({ t, onEnd }: { t: Strings; onEnd: () => void }) {
  return (
    <button type="button" className="btn btn-secondary" aria-label={t.endInterview} onClick={onEnd}>
      <EndIcon />
      <span>{t.endInterview}</span>
    </button>
  )
}
