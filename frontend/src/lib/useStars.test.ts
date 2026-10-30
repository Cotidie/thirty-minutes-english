import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { FakeEventSource } from '../test/fakeEventSource'
import type { Stars } from '../types'
import { useStars } from './useStars'

vi.mock('../api', () => ({ api: { getStars: vi.fn(), setStar: vi.fn() } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.mocked(api.getStars).mockReset().mockResolvedValue({ expressions: [11], words: [] })
  vi.mocked(api.setStar).mockReset()
})

describe('useStars', () => {
  it('loads the saved set, then flips an item and saves only that item', async () => {
    vi.mocked(api.setStar).mockResolvedValueOnce({ expressions: [11], words: [42] })
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))

    act(() => result.current.toggle('words', 42))
    expect(result.current.stars.words).toEqual([42])
    expect(api.setStar).toHaveBeenLastCalledWith(3, 'words', 42, true)
    await act(async () => {})

    vi.mocked(api.setStar).mockResolvedValueOnce({ expressions: [], words: [42] })
    act(() => result.current.toggle('expressions', 11))
    expect(api.setStar).toHaveBeenLastCalledWith(3, 'expressions', 11, false)
    await waitFor(() => expect(result.current.stars.expressions).toEqual([]))
  })

  it('shows what the server answers, with stars someone else added', async () => {
    vi.mocked(api.setStar).mockResolvedValueOnce({ expressions: [11, 12], words: [42, 43] })
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))

    act(() => result.current.toggle('words', 42))
    await waitFor(() => expect(result.current.stars).toEqual({ expressions: [11, 12], words: [42, 43] }))
  })

  it('puts the set back when the save fails', async () => {
    vi.mocked(api.setStar).mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))

    act(() => result.current.toggle('words', 42))
    expect(result.current.stars.words).toEqual([42])
    await waitFor(() => expect(result.current.stars.words).toEqual([]))
  })

  it('keeps two quick toggles when a read lands between them', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))
    const first = deferred<Stars>()
    const second = deferred<Stars>()
    vi.mocked(api.setStar).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    act(() => result.current.toggle('words', 42))
    act(() => result.current.toggle('words', 43))
    vi.mocked(api.getStars)
      .mockResolvedValue({ expressions: [11], words: [42, 43] })
      .mockResolvedValueOnce({ expressions: [11], words: [] }) // from before either save
    act(() => FakeEventSource.open[0].send('stars'))
    await act(async () => {})
    expect(result.current.stars.words).toEqual([42, 43])

    await act(async () => first.resolve({ expressions: [11], words: [42] }))
    expect(result.current.stars.words).toEqual([42, 43])
    await act(async () => second.resolve({ expressions: [11], words: [42, 43] }))
    expect(result.current.stars.words).toEqual([42, 43])
  })

  it('ignores a read that started before a save and lands after it', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))
    const slow = deferred<Stars>()
    vi.mocked(api.getStars).mockReturnValueOnce(slow.promise)
    act(() => FakeEventSource.open[0].send('stars'))

    vi.mocked(api.setStar).mockResolvedValueOnce({ expressions: [11], words: [42] })
    act(() => result.current.toggle('words', 42))
    await act(async () => {})
    await act(async () => slow.resolve({ expressions: [11], words: [] }))
    expect(result.current.stars.words).toEqual([42])
  })

  it("shows someone else's star when it is announced", async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))
    vi.mocked(api.getStars).mockResolvedValueOnce({ expressions: [11, 12], words: [] })
    act(() => FakeEventSource.open[0].send('stars'))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11, 12]))
  })

  it('shows the answer to the newest save, whichever answer lands last', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))
    const first = deferred<Stars>()
    const second = deferred<Stars>()
    vi.mocked(api.setStar).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    act(() => result.current.toggle('words', 42))
    act(() => result.current.toggle('words', 43))
    await act(async () => second.resolve({ expressions: [11], words: [42, 43] }))
    await act(async () => first.resolve({ expressions: [11], words: [42] }))
    expect(result.current.stars.words).toEqual([42, 43])
  })

  it('reads once more after the saves when an announced change had to be set aside', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))
    const save = deferred<Stars>()
    vi.mocked(api.setStar).mockReturnValueOnce(save.promise)
    act(() => result.current.toggle('words', 42))

    vi.mocked(api.getStars).mockResolvedValueOnce({ expressions: [11], words: [] }) // set aside: a save is in flight
    act(() => FakeEventSource.open[0].send('stars'))
    await act(async () => {})

    vi.mocked(api.getStars).mockResolvedValueOnce({ expressions: [11, 12], words: [42] })
    await act(async () => save.resolve({ expressions: [11], words: [42] }))
    await waitFor(() => expect(result.current.stars).toEqual({ expressions: [11, 12], words: [42] }))
  })
})
