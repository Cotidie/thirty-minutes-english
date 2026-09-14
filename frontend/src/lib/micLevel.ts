// Loudness of the live microphone, for the "we can hear you" meter. The Web
// Audio graph is read-only: it taps the same track WebRTC is already sending.

import { useEffect, useState } from 'react'

/** Peak sample distance from silence that counts as a full meter. */
const FULL_SCALE = 40
export const LEVEL_STEPS = 5

/**
 * A 0 to LEVEL_STEPS reading of how loud the stream is right now, quantised so
 * the caller re-renders on real changes rather than once a frame. Stays at 0
 * where Web Audio is missing (jsdom, an old browser); the round still works.
 */
export function useMicLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0)

  useEffect(() => {
    if (!stream || typeof AudioContext === 'undefined') return

    const context = new AudioContext()
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    const source = context.createMediaStreamSource(stream)
    source.connect(analyser)

    const samples = new Uint8Array(analyser.frequencyBinCount)
    let frame = 0
    const tick = () => {
      analyser.getByteTimeDomainData(samples)
      let peak = 0
      for (const sample of samples) peak = Math.max(peak, Math.abs(sample - 128))
      setLevel(steps(peak))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frame)
      source.disconnect()
      void context.close()
    }
  }, [stream])

  return level
}

function steps(peak: number): number {
  return Math.min(LEVEL_STEPS, Math.round((peak / FULL_SCALE) * LEVEL_STEPS))
}
