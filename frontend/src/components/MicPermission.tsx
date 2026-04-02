export function MicPermission() {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
        background: 'rgba(0,0,0,0.6)',
      }}
    >
      <div
        className="glass"
        style={{
          maxWidth: '420px',
          width: '90%',
          borderRadius: '20px',
          padding: '32px',
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: '2.5rem', marginBottom: '16px' }}>🎙️</div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '12px' }}>
          Microphone access required
        </h2>
        <p style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '20px', lineHeight: 1.6 }}>
          This app needs your microphone to have a conversation with the voice agent.
        </p>
        <div
          className="glass"
          style={{ borderRadius: '12px', padding: '16px', textAlign: 'left', fontSize: '0.875rem' }}
        >
          <p style={{ fontWeight: 600, marginBottom: '8px' }}>To enable microphone:</p>
          <p style={{ color: 'rgba(255,255,255,0.7)', marginBottom: '4px' }}>
            <strong>Chrome</strong>: Click the lock icon in the address bar → Site settings → Microphone → Allow
          </p>
          <p style={{ color: 'rgba(255,255,255,0.7)' }}>
            <strong>Firefox</strong>: Click the microphone icon in the address bar → Allow
          </p>
        </div>
      </div>
    </div>
  )
}
