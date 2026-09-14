import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Topic } from '../types'
import { TOPIC_POLL_MS, useTopics } from './useTopics'

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
    vi.mocked(api.topics).mockResolvedValueOnce({ topics: pool, pending: true }).mockResolvedValue({ topics: news, pending: false })
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
    vi.mocked(api.topics).mockResolvedValue({ topics: news, pending: false })
    const later: Topic[] = [{ text: 'A newer story', category: 'news' }, ...pool]
    vi.mocked(api.refreshTopics).mockResolvedValue({ topics: news, pending: true })
    const { result } = renderHook(() => useTopics())
    await waitFor(() => expect(result.current.topics).toEqual(news))

    vi.mocked(api.topics).mockResolvedValue({ topics: later, pending: false })
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
})
