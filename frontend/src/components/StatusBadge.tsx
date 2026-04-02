import type { ConversationState } from '../hooks/useVoiceSession'

interface Props {
  state: ConversationState
}

const STATE_LABELS: Record<ConversationState, string> = {
  idle: 'Ready',
  listening: 'Listening…',
  processing: 'Thinking…',
  agent_speaking: 'Speaking…',
  interrupted: 'Interrupted',
  reconnecting: 'Reconnecting…',
  error: 'Error',
}

const STATE_COLORS: Record<ConversationState, string> = {
  idle: 'var(--col-idle)',
  listening: 'var(--col-listening)',
  processing: 'var(--col-processing)',
  agent_speaking: 'var(--col-agent)',
  interrupted: 'var(--col-interrupted)',
  reconnecting: 'var(--col-reconnecting)',
  error: 'var(--col-error)',
}

const PULSING: ConversationState[] = ['listening', 'agent_speaking', 'reconnecting']

export function StatusBadge({ state }: Props) {
  const color = STATE_COLORS[state]
  const isPulsing = PULSING.includes(state)

  return (
    <div
      className="glass"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        padding: '8px 18px',
        borderRadius: '999px',
        fontSize: '0.875rem',
        fontWeight: 500,
        letterSpacing: '0.01em',
        userSelect: 'none',
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: color,
          boxShadow: `0 0 6px ${color}`,
          animation: isPulsing ? 'pulse-dot 1.2s ease-in-out infinite' : 'none',
          flexShrink: 0,
        }}
      />
      <span style={{ color }}>{STATE_LABELS[state]}</span>
    </div>
  )
}
