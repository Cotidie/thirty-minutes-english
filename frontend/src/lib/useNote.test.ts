import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { FakeEventSource } from '../test/fakeEventSource'
import { useNote } from './useNote'

vi.mock('../api', () => ({ api: { getNote: vi.fn(), setNote: vi.fn() } }))

/** Lets resolved promises land inside React. */
const settle = () => act(async () => {})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(api.getNote).mockResolvedValue({ text: 'hedge' })
  vi.mocked(api.setNote).mockImplementation(async (_id, text) => ({ text }))
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useNote', () => {
  it('loads the saved note, then saves the whole text once typing pauses', async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()
    expect(result.current.text).toBe('hedge')

    act(() => result.current.edit('hedge: stress'))
    act(() => result.current.edit('hedge: stress first'))
    act(() => vi.advanceTimersByTime(699))
    expect(api.setNote).not.toHaveBeenCalled()
    expect(result.current.status).toBe('saving')

    act(() => vi.advanceTimersByTime(1))
    await settle()
    expect(api.setNote).toHaveBeenCalledTimes(1)
    expect(api.setNote).toHaveBeenLastCalledWith(3, 'hedge: stress first', false)
    expect(result.current.status).toBe('saved')
  })

  it('saves at once when the box loses focus', async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()

    act(() => result.current.edit('ask about pauses'))
    act(() => result.current.flush())
    await settle()
    expect(api.setNote).toHaveBeenCalledWith(3, 'ask about pauses', false)
  })

  it('keeps what was typed when the saved note arrives late', async () => {
    const load = deferred<{ text: string }>()
    vi.mocked(api.getNote).mockReturnValue(load.promise)
    const { result } = renderHook(() => useNote(3))

    act(() => result.current.edit('typed first'))
    load.resolve({ text: 'from the server' })
    await settle()
    expect(result.current.text).toBe('typed first')
  })

  it('reports a failed save, and the next edit tries again', async () => {
    vi.mocked(api.setNote).mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useNote(3))
    await settle()

    act(() => result.current.edit('one'))
    act(() => result.current.flush())
    await settle()
    expect(result.current.status).toBe('failed')

    act(() => result.current.edit('one two'))
    act(() => result.current.flush())
    await settle()
    expect(api.setNote).toHaveBeenLastCalledWith(3, 'one two', false)
    expect(result.current.status).toBe('saved')
  })

  it('writes one save at a time and sends what was typed meanwhile after it lands', async () => {
    const first = deferred<{ text: string }>()
    vi.mocked(api.setNote).mockReturnValueOnce(first.promise)
    const { result } = renderHook(() => useNote(3))
    await settle()

    act(() => result.current.edit('a'))
    act(() => result.current.flush())
    act(() => result.current.edit('ab'))
    act(() => result.current.flush())
    expect(api.setNote).toHaveBeenCalledTimes(1)

    first.resolve({ text: 'a' })
    await settle()
    expect(api.setNote).toHaveBeenCalledTimes(2)
    expect(api.setNote).toHaveBeenLastCalledWith(3, 'ab', false)
  })

  it('saves unsaved text when the page closes, with a request that outlives the page', async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()

    act(() => result.current.edit('last thought'))
    window.dispatchEvent(new Event('pagehide'))
    expect(api.setNote).toHaveBeenCalledWith(3, 'last thought', true)
  })

  it('saves unsaved text when the session page goes away', async () => {
    const { result, unmount } = renderHook(() => useNote(3))
    await settle()

    act(() => result.current.edit('before leaving'))
    unmount()
    expect(api.setNote).toHaveBeenCalledWith(3, 'before leaving', false)
  })

  it("shows someone else's note when it is announced", async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()
    vi.mocked(api.getNote).mockResolvedValueOnce({ text: 'from the other one' })
    act(() => FakeEventSource.open[0].send('note'))
    await settle()
    expect(result.current.text).toBe('from the other one')
  })

  it('keeps what is being typed when someone else saves', async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()
    act(() => result.current.edit('hedge: mine, unsaved'))
    vi.mocked(api.getNote).mockResolvedValueOnce({ text: 'from the other one' })
    act(() => FakeEventSource.open[0].send('note'))
    await settle()
    expect(result.current.text).toBe('hedge: mine, unsaved')

    act(() => vi.advanceTimersByTime(700))
    await settle()
    expect(api.setNote).toHaveBeenLastCalledWith(3, 'hedge: mine, unsaved', false)
    expect(result.current.text).toBe('hedge: mine, unsaved')
  })

  it('ignores a read that started before a save and lands after it', async () => {
    const { result } = renderHook(() => useNote(3))
    await settle()
    const slow = deferred<{ text: string }>()
    vi.mocked(api.getNote).mockReturnValueOnce(slow.promise)
    act(() => FakeEventSource.open[0].send('note'))

    act(() => result.current.edit('hedge: saved now'))
    act(() => vi.advanceTimersByTime(700))
    await settle()
    expect(result.current.status).toBe('saved')
    await act(async () => slow.resolve({ text: 'hedge' }))
    expect(result.current.text).toBe('hedge: saved now')
  })
})
