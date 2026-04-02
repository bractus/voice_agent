/**
 * Microphone capture using MediaRecorder API.
 *
 * Records audio while the user holds the talk button and fires callbacks
 * on speech start / chunk ready / speech end. No WASM or external libs.
 */
import { useCallback, useRef, useState } from 'react'

interface UseAudioCaptureOptions {
  onSpeechStart: () => void
  onAudioChunk: (buffer: ArrayBuffer) => void
  onSpeechEnd: () => void
}

interface UseAudioCaptureResult {
  isListening: boolean
  permissionDenied: boolean
  startRecording: () => void
  stopRecording: () => void
}

export function useAudioCapture({
  onSpeechStart,
  onAudioChunk,
  onSpeechEnd,
}: UseAudioCaptureOptions): UseAudioCaptureResult {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [isListening, setIsListening] = useState(false)
  const [permissionDenied, setPermissionDenied] = useState(false)

  const startRecording = useCallback(async () => {
    if (isListening) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const buffer = await blob.arrayBuffer()
        onAudioChunk(buffer)
        onSpeechEnd()
        setIsListening(false)
      }

      recorder.start(100)
      setIsListening(true)
      onSpeechStart()
    } catch {
      setPermissionDenied(true)
    }
  }, [isListening, onSpeechStart, onAudioChunk, onSpeechEnd])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }, [])

  return { isListening, permissionDenied, startRecording, stopRecording }
}
