import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChunks } from './useChunks'

/** Stands in for the browser's observer: the test says when the sentinel comes near the viewport. */
class FakeObserver {
  static live: FakeObserver[] = []
  private readonly callback: IntersectionObserverCallback
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
  }
  observe() {
    FakeObserver.live.push(this)
  }
  disconnect() {
    FakeObserver.live = FakeObserver.live.filter((o) => o !== this)
  }
  near() {
    this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
  }
}

const items = Array.from({ length: 120 }, (_, i) => i)

function scrollToSentinel() {
  act(() => FakeObserver.live.at(-1)!.near())
}

beforeEach(() => {
  FakeObserver.live = []
  vi.stubGlobal('IntersectionObserver', FakeObserver)
})

afterEach(() => vi.unstubAllGlobals())

describe('useChunks', () => {
  it('shows the first fifty, and fifty more each time the sentinel comes near', () => {
    const { result } = renderHook(() => useChunks(items, 'all'))
    expect(result.current.shown).toHaveLength(50)
    expect(result.current.more).toBe(true)

    act(() => result.current.sentinel(document.createElement('div')))
    scrollToSentinel()
    expect(result.current.shown).toHaveLength(100)
    scrollToSentinel()
    expect(result.current.shown).toEqual(items)
    expect(result.current.more).toBe(false)
    expect(FakeObserver.live).toEqual([]) // nothing left to watch for
  })

  it('starts over at fifty for a new search, but keeps its place when an item goes', () => {
    const { result, rerender } = renderHook(({ list, key }) => useChunks(list, key), { initialProps: { list: items, key: 'all' } })
    act(() => result.current.sentinel(document.createElement('div')))
    scrollToSentinel()
    expect(result.current.shown).toHaveLength(100)

    rerender({ list: items.filter((i) => i !== 3), key: 'all' })
    expect(result.current.shown).toHaveLength(100)

    rerender({ list: items, key: 'casual' })
    expect(result.current.shown).toHaveLength(50)
  })
})
