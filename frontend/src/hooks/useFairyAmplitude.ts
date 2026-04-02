/**
 * Derives a normalised amplitude value (0.0–1.0) from a Web Audio AnalyserNode
 * at 60fps using requestAnimationFrame.
 */
import { useEffect, useRef, useState } from 'react'

export function useFairyAmplitude(analyserNode: AnalyserNode | null): number {
  const [amplitude, setAmplitude] = useState(0)
  const rafRef = useRef<number | null>(null)
  const dataArrayRef = useRef<Float32Array | null>(null)

  useEffect(() => {
    if (!analyserNode) {
      setAmplitude(0)
      return
    }

    const bufferLength = analyserNode.frequencyBinCount
    dataArrayRef.current = new Float32Array(bufferLength) as Float32Array<ArrayBuffer>

    const tick = () => {
      rafRef.current = requestAnimationFrame(tick)
      analyserNode.getFloatFrequencyData(dataArrayRef.current as Float32Array<ArrayBuffer>)

      // Compute RMS from frequency bin magnitudes (dB values)
      // Convert dB to linear, then compute RMS
      let sumSquares = 0
      const data = dataArrayRef.current!
      for (let i = 0; i < bufferLength; i++) {
        const linear = Math.pow(10, data[i] / 20)
        sumSquares += linear * linear
      }
      const rms = Math.sqrt(sumSquares / bufferLength)
      // Normalise: typical RMS range ~0.001–0.3 → map to 0–1
      const normalised = Math.min(1, rms / 0.3)
      setAmplitude(normalised)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [analyserNode])

  return amplitude
}
