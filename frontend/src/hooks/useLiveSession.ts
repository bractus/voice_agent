/**
 * The browser side of a GPT-Live session: a WebRTC peer connection carrying the
 * mic up and the interviewer's voice down, plus the `oai-events` data channel.
 *
 * The server creates the session (it holds the API key); this hook only posts
 * the SDP offer and applies the answer. Analysers on both streams feed the
 * fairy. See specs/002-gpt-live-interview/research.md §1 and §7.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { startLive, type InterviewLanguage, type InterviewType, type Seniority } from '../services/liveApi'

type LiveEvent = Record<string, unknown>

export interface LiveSession {
  start: (
    sessionId: string,
    type: InterviewType,
    language: InterviewLanguage,
    role?: string | null,
    seniority?: Seniority,
  ) => Promise<void>
  close: () => void
  setMuted: (muted: boolean) => void
  sendEvent: (event: LiveEvent) => void
  /** Receives every event arriving on the data channel. */
  setEventHandler: (handler: ((event: LiveEvent) => void) | null) => void
  /** Called once when the WebRTC connection fails or stays disconnected for 2 s. */
  setDisconnectHandler: (handler: (() => void) | null) => void
  muted: boolean
  connected: boolean
  permissionDenied: boolean
  micAnalyser: AnalyserNode | null
  remoteAnalyser: AnalyserNode | null
}

const DISCONNECT_GRACE_MS = 2000

export function useLiveSession(): LiveSession {
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const channelRef = useRef<RTCDataChannel | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const audioElRef = useRef<HTMLAudioElement | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const eventHandlerRef = useRef<((event: LiveEvent) => void) | null>(null)
  const disconnectHandlerRef = useRef<(() => void) | null>(null)
  const disconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reportedLossRef = useRef(false)

  const [muted, setMutedState] = useState(false)
  const [connected, setConnected] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [micAnalyser, setMicAnalyser] = useState<AnalyserNode | null>(null)
  const [remoteAnalyser, setRemoteAnalyser] = useState<AnalyserNode | null>(null)

  const reportLoss = useCallback(() => {
    if (reportedLossRef.current) return
    reportedLossRef.current = true
    disconnectHandlerRef.current?.()
  }, [])

  const close = useCallback(() => {
    if (disconnectTimerRef.current) clearTimeout(disconnectTimerRef.current)
    disconnectTimerRef.current = null
    // A deliberate close is not a lost connection.
    reportedLossRef.current = true
    channelRef.current?.close()
    pcRef.current?.close()
    micStreamRef.current?.getTracks().forEach((t) => t.stop())
    if (audioElRef.current) audioElRef.current.srcObject = null
    ctxRef.current?.close().catch(() => {})
    pcRef.current = null
    channelRef.current = null
    micStreamRef.current = null
    ctxRef.current = null
    setConnected(false)
    setMicAnalyser(null)
    setRemoteAnalyser(null)
  }, [])

  const start = useCallback(
    async (
      sessionId: string,
      type: InterviewType,
      language: InterviewLanguage,
      role: string | null = null,
      seniority: Seniority = 'mid',
    ) => {
      if (pcRef.current) return
      let mic: MediaStream
      try {
        mic = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        })
      } catch {
        setPermissionDenied(true)
        throw new Error('Microphone access is needed for the interview.')
      }
      micStreamRef.current = mic
      reportedLossRef.current = false

      const ctx = new AudioContext()
      ctxRef.current = ctx
      const micNode = ctx.createAnalyser()
      micNode.fftSize = 1024
      ctx.createMediaStreamSource(mic).connect(micNode)
      setMicAnalyser(micNode)

      const pc = new RTCPeerConnection()
      pcRef.current = pc
      mic.getAudioTracks().forEach((track) => pc.addTrack(track, mic))

      pc.ontrack = (e) => {
        const [remote] = e.streams
        if (!remote) return
        // Playing through an <audio> element gives the echo canceller its reference
        // signal and makes Chrome pull the stream for the analyser.
        const audio = audioElRef.current ?? new Audio()
        audio.autoplay = true
        audio.srcObject = remote
        audioElRef.current = audio
        audio.play().catch(() => {})
        const remoteNode = ctx.createAnalyser()
        remoteNode.fftSize = 1024
        ctx.createMediaStreamSource(remote).connect(remoteNode)
        setRemoteAnalyser(remoteNode)
      }

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState
        setConnected(state === 'connected')
        if (state === 'connected' && disconnectTimerRef.current) {
          clearTimeout(disconnectTimerRef.current)
          disconnectTimerRef.current = null
        } else if (state === 'failed') {
          reportLoss()
        } else if (state === 'disconnected' && !disconnectTimerRef.current) {
          disconnectTimerRef.current = setTimeout(() => {
            disconnectTimerRef.current = null
            if (pc.connectionState !== 'connected') reportLoss()
          }, DISCONNECT_GRACE_MS)
        }
      }

      // The data channel must exist before the offer is created.
      const channel = pc.createDataChannel('oai-events')
      channelRef.current = channel
      channel.onmessage = (e) => {
        try {
          eventHandlerRef.current?.(JSON.parse(e.data))
        } catch {
          /* ignore malformed events */
        }
      }

      try {
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        const result = await startLive(sessionId, type, language, offer.sdp ?? '', role, seniority)
        await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp })
      } catch (err) {
        close()
        throw err
      }
    },
    [close, reportLoss],
  )

  const sendEvent = useCallback((event: LiveEvent) => {
    const channel = channelRef.current
    if (channel?.readyState === 'open') channel.send(JSON.stringify(event))
  }, [])

  const setMuted = useCallback(
    (next: boolean) => {
      // Stop sending audio, and tell the model the silence is deliberate (FR-016).
      micStreamRef.current?.getAudioTracks().forEach((t) => (t.enabled = !next))
      sendEvent({ type: next ? 'session.input_audio.mute' : 'session.input_audio.unmute' })
      setMutedState(next)
    },
    [sendEvent],
  )

  const setEventHandler = useCallback((handler: ((event: LiveEvent) => void) | null) => {
    eventHandlerRef.current = handler
  }, [])

  const setDisconnectHandler = useCallback((handler: (() => void) | null) => {
    disconnectHandlerRef.current = handler
  }, [])

  useEffect(() => close, [close])

  return {
    start,
    close,
    setMuted,
    sendEvent,
    setEventHandler,
    setDisconnectHandler,
    muted,
    connected,
    permissionDenied,
    micAnalyser,
    remoteAnalyser,
  }
}
