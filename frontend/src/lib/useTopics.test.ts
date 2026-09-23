import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Topic } from '../types'
import { TOPIC_POLL_LIMIT, TOPIC_POLL_MS, useTopics } from './useTopics'

vi.mock('../api', () => ({ api: { topics: vi.fn(), refreshTopics: vi.fn() } }))

const pool: Topic[] = [{ text: 'The Cold War space race', category: 'history' }]
const news: Topic[] = [{ text: 'Who pays when the grid runs short', category: 'news' }, ...pool]

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useTopics', () => {
  it('keeps asking while the news half is pending, then stops', async () => {
    vi.mocked(api.topics).mockResolvedValueOnce({ topics: pool, pending: true, error: null, labels: {} }).mockResolvedValue({ topics: news, pending: false, error: null, labels: {} })
    const { result } = renderHook(() => useTopics())
    await waitFor(() => expect(result.current.pending).toBe(true))

    await act(async () => {
      vi.advanceTimersByTime(TOPIC_POLL_MS)
    })
    await waitFor(() => expect(result.current.pending).toBe(false))
    expect(result.current.topics).toEqual(news)
    expect(api.topics).toHaveBeenCalledTimes(2)
  })

  it('refresh deals a new list and polls again until it lands', async () => {
    vi.mocked(api.topics).mockResolvedValue({ topics: news, pending: false, error: null, labels: {} })
    const later: Topic[] = [{ text: 'A newer story', category: 'news' }, ...pool]
    vi.mocked(api.refreshTopics).mockResolvedValue({ topics: news, pending: true, error: null, labels: {} })
    const { result } = renderHook(() => useTopics())
    await waitFor(() => expect(result.current.topics).toEqual(news))

    vi.mocked(api.topics).mockResolvedValue({ topics: later, pending: false, error: null, labels: {} })
    await act(async () => {
      result.current.refresh()
    })
    expect(result.current.pending).toBe(true)
    await act(async () => {
      vi.advanceTimersByTime(TOPIC_POLL_MS)
    })
    await waitFor(() => expect(result.current.topics).toEqual(later))
    expect(result.current.pending).toBe(false)
  })

  it('gives up after the poll limit so the refresh button comes back', async () => {
    vi.mocked(api.topics).mockResolvedValue({ topics: pool, pending: true, error: null, labels: {} })
    const { result } = renderHook(() => useTopics())
    await waitFor(() => expect(result.current.pending).toBe(true))

    for (let i = 0; i < TOPIC_POLL_LIMIT; i++) {
      await act(async () => {
        vi.advanceTimersByTime(TOPIC_POLL_MS)
      })
    }
    await waitFor(() => expect(result.current.pending).toBe(false))
    expect(api.topics).toHaveBeenCalledTimes(TOPIC_POLL_LIMIT + 1)
  })

  it('passes on why the news half is missing', async () => {
    vi.mocked(api.topics).mockResolvedValue({ topics: pool, pending: false, error: 'claude exited 1', labels: {} })
    const { result } = renderHook(() => useTopics())
    await waitFor(() => expect(result.current.error).toBe('claude exited 1'))
    expect(result.current.pending).toBe(false)
  })
})
