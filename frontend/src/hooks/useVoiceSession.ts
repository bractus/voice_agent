/**
 * Orchestrates WebSocket, audio capture, and audio playback into a
 * single conversation state machine.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { WsClient } from '../services/wsClient'
import { useAudioCapture } from './useAudioCapture'
import { useAudioPlayer } from './useAudioPlayer'

export type ConversationState =
  | 'idle'
  | 'listening'
  | 'processing'
  | 'agent_speaking'
  | 'interrupted'
  | 'reconnecting'
  | 'error'

interface UseVoiceSessionResult {
  state: ConversationState
  connect: () => void
  isReady: boolean
  errorMessage: string
  analyserNode: AnalyserNode | null
  permissionDenied: boolean
  startTalking: () => void
  stopTalking: () => void
  isListening: boolean
}

function getSessionId(): string {
  let id = sessionStorage.getItem('voice_session_id')
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem('voice_session_id', id)
  }
  return id
}

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const sessionId = getSessionId()
  return `${proto}://${window.location.host}/ws/${sessionId}`
}

export function useVoiceSession(): UseVoiceSessionResult {
  const [state, setState] = useState<ConversationState>('reconnecting')
  const [errorMessage, setErrorMessage] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const clientRef = useRef<WsClient | null>(null)
  const audioPlayer = useAudioPlayer()

  const handleSpeechStart = useCallback(() => {
    if (audioPlayer.isPlaying) {
      audioPlayer.stop()
      clientRef.current?.send(JSON.stringify({ type: 'barge_in' }))
    }
    setState('listening')
  }, [audioPlayer])

  const handleAudioChunk = useCallback((buffer: ArrayBuffer) => {
    clientRef.current?.send(buffer)
  }, [])

  const handleSpeechEnd = useCallback(() => {
    clientRef.current?.send(JSON.stringify({ type: 'end_utterance' }))
  }, [])

  const { isListening, permissionDenied, startRecording, stopRecording } = useAudioCapture({
    onSpeechStart: handleSpeechStart,
    onAudioChunk: handleAudioChunk,
    onSpeechEnd: handleSpeechEnd,
  })

  const connect = useCallback(() => {
    if (clientRef.current) return
    const wsUrl = getWsUrl()
    const sessionId = getSessionId()
    const client = new WsClient()
    clientRef.current = client

    client.onConnectionState = (connected) => {
      setIsConnected(connected)
      setState(connected ? 'idle' : 'reconnecting')
    }

    client.onTextFrame = (msg) => {
      const type = msg.type as string
      if (type === 'state_change') {
        setState(msg.state as ConversationState)
      } else if (type === 'error') {
        setErrorMessage(msg.message as string)
        setState('idle')
      }
    }

    client.onBinaryFrame = (data) => {
      audioPlayer.enqueue(data)
    }

    client.connect(wsUrl, sessionId)
  }, [audioPlayer])

  useEffect(() => {
    return () => {
      clientRef.current?.disconnect()
      clientRef.current = null
    }
  }, [])

  return {
    state,
    connect,
    isReady: isConnected && !permissionDenied,
    errorMessage,
    analyserNode: audioPlayer.analyserNode,
    permissionDenied,
    startTalking: startRecording,
    stopTalking: stopRecording,
    isListening,
  }
}
