/**
 * Web Audio API queue-based PCM player.
 *
 * Accepts raw PCM binary frames (16-bit, 16 kHz, mono) from the WebSocket,
 * wraps them in a WAV envelope, decodes, and plays them in sequence without
 * gaps. Exposes an AnalyserNode for fairy dot visualisation.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

/** Prepend a 44-byte RIFF WAV header to raw 16-bit signed PCM (16 kHz mono). */
function pcmToWav(pcm: ArrayBuffer): ArrayBuffer {
  const dataLen = pcm.byteLength
  const header = new ArrayBuffer(44)
  const v = new DataView(header)
  const w = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i))
  }
  w(0, 'RIFF'); v.setUint32(4, 36 + dataLen, true)
  w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true)   // chunk size
  v.setUint16(20, 1, true)    // PCM
  v.setUint16(22, 1, true)    // mono
  v.setUint32(24, 16000, true) // sample rate
  v.setUint32(28, 32000, true) // byte rate
  v.setUint16(32, 2, true)    // block align
  v.setUint16(34, 16, true)   // bits per sample
  w(36, 'data'); v.setUint32(40, dataLen, true)
  const out = new Uint8Array(44 + dataLen)
  out.set(new Uint8Array(header), 0)
  out.set(new Uint8Array(pcm), 44)
  return out.buffer
}

export interface UseAudioPlayerResult {
  enqueue: (pcmBuffer: ArrayBuffer) => void
  stop: () => void
  isPlaying: boolean
  analyserNode: AnalyserNode | null
}

export function useAudioPlayer(): UseAudioPlayerResult {
  const ctxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const nextPlayTimeRef = useRef(0)
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([])
  const [isPlaying, setIsPlaying] = useState(false)
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null)

  const getCtx = useCallback((): { ctx: AudioContext; analyser: AnalyserNode } => {
    if (!ctxRef.current || ctxRef.current.state === 'closed') {
      const ctx = new AudioContext()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.8
      analyser.connect(ctx.destination)
      ctxRef.current = ctx
      analyserRef.current = analyser
      setAnalyserNode(analyser)
    }
    return { ctx: ctxRef.current, analyser: analyserRef.current! }
  }, [])

  const enqueue = useCallback(
    async (pcmBuffer: ArrayBuffer) => {
      const { ctx, analyser } = getCtx()
      if (ctx.state === 'suspended') await ctx.resume()

      const wavBuffer = pcmToWav(pcmBuffer)
      let audioBuffer: AudioBuffer
      try {
        audioBuffer = await ctx.decodeAudioData(wavBuffer)
      } catch (e) {
        console.warn('[AudioPlayer] decodeAudioData failed', e)
        return
      }

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(analyser)
      activeSourcesRef.current.push(source)

      const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current)
      source.start(startAt)
      nextPlayTimeRef.current = startAt + audioBuffer.duration

      setIsPlaying(true)
      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source)
        if (activeSourcesRef.current.length === 0) {
          setIsPlaying(false)
        }
      }
    },
    [getCtx]
  )

  const stop = useCallback(() => {
    for (const src of activeSourcesRef.current) {
      try { src.stop() } catch { /* already stopped */ }
    }
    activeSourcesRef.current = []
    nextPlayTimeRef.current = 0
    setIsPlaying(false)
  }, [])

  useEffect(() => {
    return () => {
      stop()
      ctxRef.current?.close()
    }
  }, [stop])

  return { enqueue, stop, isPlaying, analyserNode }
}
