import { Component, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; message: string }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(err: unknown): State {
    return { hasError: true, message: String(err) }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          width: '100vw', height: '100vh', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          background: 'var(--page-bg, #0d0015)',
        }}>
          <div className="glass" style={{ padding: '32px', borderRadius: '20px', maxWidth: '480px', color: '#f87171' }}>
            <h2 style={{ marginBottom: '12px' }}>Something went wrong</h2>
            <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', color: 'rgba(255,255,255,0.6)' }}>
              {this.state.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
