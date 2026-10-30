import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { FakeEventSource } from '../test/fakeEventSource'
import { useSessionGone, useSessionResource } from './sessionChanges'

const settle = () => act(async () => {})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const stream = () => FakeEventSource.open[0]

beforeEach(() => {
  FakeEventSource.instances = []
})
afterEach(() => {
  vi.useRealTimers()
})

test('reads once at first, and again when that change is announced', async () => {
  const read = vi.fn(async () => 'text')
  const show = vi.fn()
  renderHook(() => useSessionResource(3, 'note', read, show))
  await settle()
  expect(read).toHaveBeenCalledTimes(1)
  expect(show).toHaveBeenCalledWith('text')

  act(() => stream().send('note'))
  await settle()
  expect(read).toHaveBeenCalledTimes(2)

  act(() => stream().send('stars'))
  await settle()
  expect(read).toHaveBeenCalledTimes(2)
})

test('a session has one stream however many read it, closed with the last of them', async () => {
  const first = renderHook(() => useSessionResource(3, 'note', async () => 1, vi.fn()))
  const second = renderHook(() => useSessionResource(3, 'stars', async () => 2, vi.fn()))
  await settle()
  expect(FakeEventSource.open).toHaveLength(1)
  expect(stream().url).toBe('/api/sessions/3/events')

  first.unmount()
  expect(FakeEventSource.open).toHaveLength(1)
  second.unmount()
  expect(FakeEventSource.open).toHaveLength(0)
})

test('reads never overlap: changes during a read make one more read after it', async () => {
  const reads = [deferred<string>(), deferred<string>()]
  let next = 0
  const read = vi.fn(() => reads[next++].promise)
  const show = vi.fn()
  renderHook(() => useSessionResource(3, 'records', read, show))
  await settle()
  act(() => {
    stream().send('records')
    stream().send('records')
    stream().send('records')
  })
  expect(read).toHaveBeenCalledTimes(1)

  reads[0].resolve('old')
  await settle()
  expect(read).toHaveBeenCalledTimes(2)
  expect(show).toHaveBeenLastCalledWith('old')

  reads[1].resolve('new')
  await settle()
  expect(read).toHaveBeenCalledTimes(2)
  expect(show).toHaveBeenLastCalledWith('new')
})

test('every time the stream comes up, everything is read again, since nothing missed is sent', async () => {
  const note = vi.fn(async () => 1)
  const stars = vi.fn(async () => 2)
  renderHook(() => useSessionResource(3, 'note', note, vi.fn()))
  renderHook(() => useSessionResource(3, 'stars', stars, vi.fn()))
  await settle()
  act(() => stream().connect())
  await settle()
  expect([note.mock.calls.length, stars.mock.calls.length]).toEqual([2, 2])

  act(() => stream().drop())
  act(() => stream().connect())
  await settle()
  expect([note.mock.calls.length, stars.mock.calls.length]).toEqual([3, 3])
})

test('a stream that will not come back makes the session be read, then tries again later', async () => {
  vi.useFakeTimers()
  const session = vi.fn(async () => 1)
  renderHook(() => useSessionResource(3, 'session', session, vi.fn()))
  await settle()
  const dropped = stream()
  act(() => dropped.drop(true))
  await settle()
  expect(session).toHaveBeenCalledTimes(2)
  expect(FakeEventSource.open).toHaveLength(0)

  act(() => vi.advanceTimersByTime(5000))
  expect(FakeEventSource.open).toHaveLength(1)
  expect(stream()).not.toBe(dropped)
})

test('gone is heard, and the stream stays closed', async () => {
  vi.useFakeTimers()
  const onGone = vi.fn()
  renderHook(() => useSessionGone(3, onGone))
  await settle()
  act(() => stream().send('gone'))
  expect(onGone).toHaveBeenCalledOnce()
  expect(FakeEventSource.open).toHaveLength(0)
  act(() => vi.advanceTimersByTime(60000))
  expect(FakeEventSource.open).toHaveLength(0)
})

test('what lands after leaving a session is dropped', async () => {
  const read = deferred<string>()
  const show = vi.fn()
  const { unmount } = renderHook(() => useSessionResource(3, 'note', () => read.promise, show))
  await settle()
  unmount()
  read.resolve('late')
  await settle()
  expect(show).not.toHaveBeenCalled()
})

test('moving to another session reads that one and leaves the old stream', async () => {
  const read = vi.fn(async (id: number) => id)
  const show = vi.fn()
  const { rerender } = renderHook(({ id }) => useSessionResource(id, 'note', () => read(id), show), { initialProps: { id: 3 } })
  await settle()
  rerender({ id: 4 })
  await settle()
  expect(show).toHaveBeenLastCalledWith(4)
  expect(FakeEventSource.open.map((s) => s.url)).toEqual(['/api/sessions/4/events'])
})

test('a failed read is told to the page and does not stop the next', async () => {
  const read = vi.fn<() => Promise<string>>().mockRejectedValueOnce(new Error('offline')).mockResolvedValue('back')
  const show = vi.fn()
  const onError = vi.fn()
  renderHook(() => useSessionResource(3, 'note', read, show, onError))
  await settle()
  expect(onError).toHaveBeenCalledOnce()
  act(() => stream().send('note'))
  await settle()
  expect(show).toHaveBeenCalledWith('back')
})
