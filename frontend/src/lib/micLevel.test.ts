import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LEVEL_STEPS, useMicLevel } from './micLevel'

/** A Web Audio graph whose analyser reports one fixed peak. */
function stubAudio(peak: number) {
  const source = { connect: vi.fn(), disconnect: vi.fn() }
  const close = vi.fn()
  const analyser = {
    fftSize: 0,
    frequencyBinCount: 4,
    getByteTimeDomainData: (out: Uint8Array) => out.fill(128 + peak),
  }
  vi.stubGlobal(
    'AudioContext',
    class {
      createAnalyser = () => analyser
      createMediaStreamSource = () => source
      close = close
    },
  )
  // Run one frame, then hand back ids without recursing.
  let frames = 0
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    if (frames++ === 0) cb(0)
    return frames
  })
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  return { source, close }
}

/** One stable object: a new stream on every render would restart the meter. */
const stream = {} as MediaStream

afterEach(() => vi.unstubAllGlobals())

describe('useMicLevel', () => {
  it('reads silence as no bars and a loud peak as a full meter', () => {
    stubAudio(0)
    expect(renderHook(() => useMicLevel(stream)).result.current).toBe(0)

    stubAudio(60)
    expect(renderHook(() => useMicLevel(stream)).result.current).toBe(LEVEL_STEPS)
  })

  it('scales a speaking-level peak somewhere in between', () => {
    stubAudio(16)
    const { result } = renderHook(() => useMicLevel(stream))
    expect(result.current).toBeGreaterThan(0)
    expect(result.current).toBeLessThan(LEVEL_STEPS)
  })

  it('tears the graph down when the round ends', () => {
    const { source, close } = stubAudio(20)
    const { unmount } = renderHook(() => useMicLevel(stream))
    unmount()
    expect(source.disconnect).toHaveBeenCalled()
    expect(close).toHaveBeenCalled()
  })

  it('stays at zero without a stream, and where Web Audio is missing', () => {
    stubAudio(60)
    expect(renderHook(() => useMicLevel(null)).result.current).toBe(0)

    vi.unstubAllGlobals()
    vi.stubGlobal('AudioContext', undefined)
    expect(renderHook(() => useMicLevel(stream)).result.current).toBe(0)
  })
})
