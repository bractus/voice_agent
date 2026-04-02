/**
 * WebSocket client with automatic reconnection.
 *
 * Multiplexes binary PCM audio frames and JSON text control frames
 * over a single WebSocket connection.
 */

export type TextFrameHandler = (msg: Record<string, unknown>) => void
export type BinaryFrameHandler = (data: ArrayBuffer) => void
export type ConnectionStateHandler = (connected: boolean) => void

const INITIAL_BACKOFF_MS = 500
const MAX_BACKOFF_MS = 5000
const MAX_RETRIES = 10

export class WsClient {
  private ws: WebSocket | null = null
  private url = ''
  private sessionId = ''
  private retryCount = 0
  private retryTimeout: ReturnType<typeof setTimeout> | null = null
  private stopped = false

  onTextFrame: TextFrameHandler = () => {}
  onBinaryFrame: BinaryFrameHandler = () => {}
  onConnectionState: ConnectionStateHandler = () => {}

  connect(url: string, sessionId: string): void {
    this.url = url
    this.sessionId = sessionId
    this.stopped = false
    this._open()
  }

  disconnect(): void {
    this.stopped = true
    this.retryCount = 0
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout)
      this.retryTimeout = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  send(data: string | ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data)
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  private _open(): void {
    if (this.stopped) return
    const ws = new WebSocket(this.url)
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    ws.onopen = () => {
      this.retryCount = 0
      // Send start_session now that the socket is actually open
      ws.send(JSON.stringify({ type: 'start_session', session_id: this.sessionId }))
      this.onConnectionState(true)
    }

    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        this.onBinaryFrame(ev.data)
      } else if (typeof ev.data === 'string') {
        try {
          const parsed = JSON.parse(ev.data) as Record<string, unknown>
          this.onTextFrame(parsed)
        } catch {
          console.warn('[WsClient] invalid JSON:', ev.data)
        }
      }
    }

    ws.onclose = () => {
      this.onConnectionState(false)
      this._scheduleReconnect()
    }

    ws.onerror = () => {
      // onclose fires after onerror; reconnect handled there
    }
  }

  private _scheduleReconnect(): void {
    if (this.stopped || this.retryCount >= MAX_RETRIES) return
    const delay = Math.min(INITIAL_BACKOFF_MS * 2 ** this.retryCount, MAX_BACKOFF_MS)
    this.retryCount++
    this.retryTimeout = setTimeout(() => {
      this._open()
    }, delay)
  }
}
