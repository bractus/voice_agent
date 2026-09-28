import type { Strings } from '../i18n'
import { MicIcon, MicOffIcon } from './icons'

/** Mutes the microphone: no audio leaves the machine, and the interviewer is told (FR-016). */
export function MuteButton({ t, muted, onToggle }: { t: Strings; muted: boolean; onToggle: () => void }) {
  const label = muted ? t.unmute : t.mute
  return (
    <button type="button" className="btn btn-secondary" aria-pressed={muted} aria-label={label} onClick={onToggle}>
      {muted ? <MicOffIcon /> : <MicIcon />}
      <span className="btn-text-optional">{label}</span>
    </button>
  )
}
