import type { ConversationState } from '../hooks/useVoiceSession'

interface Props {
  amplitude: number
  state: ConversationState
}

export function FairyDot({ amplitude, state }: Props) {
  const BASE_R = 40
  const MAX_DELTA_R = 60
  const BASE_GLOW = 20
  const MAX_DELTA_GLOW = 80

  const r = BASE_R + amplitude * MAX_DELTA_R
  const glowSize = BASE_GLOW + amplitude * MAX_DELTA_GLOW
  const glowAlpha = 0.3 + amplitude * 0.7

  const isIdle = amplitude < 0.05
  const isReconnecting = state === 'reconnecting'

  let animation = 'none'
  if (isReconnecting) animation = 'fairy-reconnect 1.8s ease-in-out infinite'
  else if (isIdle) animation = 'fairy-idle 2s ease-in-out infinite'

  const diameter = `${(BASE_R + MAX_DELTA_R) * 2}px`

  return (
    <div
      style={{
        width: diameter,
        height: diameter,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: `${r * 2}px`,
          height: `${r * 2}px`,
          borderRadius: '50%',
          background: 'radial-gradient(circle at 38% 35%, #ffb3e6 0%, #ff50c8 40%, #c020a0 100%)',
          boxShadow: `0 0 ${glowSize}px rgba(255, 100, 200, ${glowAlpha}), 0 0 ${glowSize * 0.5}px rgba(200, 30, 160, ${glowAlpha * 0.6})`,
          animation,
          transition: isIdle ? 'none' : 'width 33ms linear, height 33ms linear, box-shadow 33ms linear',
          willChange: 'width, height, box-shadow',
        }}
      />
    </div>
  )
}
