import { useEffect } from 'react'
import { useVoiceSession } from './hooks/useVoiceSession'
import { useFairyAmplitude } from './hooks/useFairyAmplitude'
import { FairyDot } from './components/FairyDot'
import { StatusBadge } from './components/StatusBadge'
import { MicPermission } from './components/MicPermission'

export default function App() {
  const {
    state,
    connect,
    permissionDenied,
    errorMessage,
    analyserNode,
    startTalking,
    stopTalking,
    isListening,
    isReady,
  } = useVoiceSession()

  const amplitude = useFairyAmplitude(analyserNode)

  useEffect(() => {
    connect()
  }, [connect])

  const canTalk = isReady && state !== 'processing' && state !== 'agent_speaking'

  return (
    <div
      style={{
        width: '100%',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
        userSelect: 'none',
      }}
    >
      {/* Central fairy — press and hold to talk */}
      <div
        style={{ cursor: canTalk ? 'pointer' : 'default' }}
        onMouseDown={canTalk ? startTalking : undefined}
        onMouseUp={isListening ? stopTalking : undefined}
        onTouchStart={canTalk ? startTalking : undefined}
        onTouchEnd={isListening ? stopTalking : undefined}
      >
        <FairyDot amplitude={isListening ? 0.4 : amplitude} state={state} />
      </div>

      {/* Hint label */}
      <p
        className="glass"
        style={{
          marginTop: '28px',
          padding: '6px 16px',
          borderRadius: '999px',
          fontSize: '0.8rem',
          color: 'rgba(255,255,255,0.55)',
          letterSpacing: '0.03em',
        }}
      >
        {isListening
          ? 'Release to send…'
          : canTalk
          ? 'Hold to talk'
          : state === 'processing'
          ? 'Thinking…'
          : state === 'agent_speaking'
          ? 'Listening…'
          : state === 'reconnecting'
          ? 'Connecting…'
          : 'Hold to talk'}
      </p>

      {/* Status badge — fixed bottom-left */}
      <div style={{ position: 'fixed', bottom: '24px', left: '24px' }}>
        <StatusBadge state={state} />
      </div>

      {/* Error message — fixed bottom-centre */}
      {errorMessage && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            left: '50%',
            transform: 'translateX(-50%)',
          }}
        >
          <div
            className="glass"
            style={{
              padding: '8px 18px',
              borderRadius: '999px',
              fontSize: '0.875rem',
              color: 'var(--col-error)',
              whiteSpace: 'nowrap',
            }}
          >
            {errorMessage}
          </div>
        </div>
      )}

      {/* Microphone permission overlay */}
      {permissionDenied && <MicPermission />}
    </div>
  )
}
