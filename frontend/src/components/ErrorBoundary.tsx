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
        <div className="dialog-backdrop">
          <div className="dialog" role="alert">
            <h2>Something went wrong · Algo deu errado</h2>
            <pre style={{ fontSize: '0.75rem', whiteSpace: 'pre-wrap', color: 'var(--ink-muted)' }}>
              {this.state.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
