import type { ReactNode } from 'react'
import type { Strings } from '../i18n'

export type SignalLevel = 'idle' | 'live' | 'active' | 'wait'

interface Props {
  t: Strings
  /** The fairy perches here while the setup screen is shown. */
  perchRef?: (el: HTMLElement | null) => void
  center?: ReactNode
  signal: { level: SignalLevel; text: string }
  /** On small screens, drop the signal (the fairy and caption already show who is talking). */
  compact?: boolean
  children?: ReactNode
}

/** The one bar every screen shares: wordmark, context, readouts, and who is speaking. */
export function TopBar({ t, perchRef, center, signal, compact, children }: Props) {
  return (
    <header className="topbar" data-compact={compact ? 'true' : undefined}>
      <div className="wordmark">
        {t.appName}
        {perchRef ? (
          <span ref={perchRef} className="wordmark-perch" data-fairy-scale="0.42" aria-hidden="true" />
        ) : (
          <span className="wordmark-perch" aria-hidden="true" />
        )}
      </div>
      <div className="topbar-center">{center}</div>
      <div className="topbar-right">
        {children}
        <span className="signal" data-level={signal.level} role="status" aria-label={signal.text}>
          <span className="signal-dot" aria-hidden="true" />
          <span className="signal-text">{signal.text}</span>
        </span>
      </div>
    </header>
  )
}
