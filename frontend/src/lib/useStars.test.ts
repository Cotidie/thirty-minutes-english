import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { useStars } from './useStars'

vi.mock('../api', () => ({ api: { getStars: vi.fn(), setStars: vi.fn() } }))

beforeEach(() => {
  vi.mocked(api.getStars).mockResolvedValue({ expressions: [11], words: [] })
  vi.mocked(api.setStars).mockImplementation(async (_id, stars) => stars)
})

describe('useStars', () => {
  it('loads the saved set, then flips an item and saves the whole set', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))

    act(() => result.current.toggle('words', 42))
    expect(result.current.stars.words).toEqual([42])
    expect(api.setStars).toHaveBeenLastCalledWith(3, { expressions: [11], words: [42] })

    act(() => result.current.toggle('expressions', 11))
    expect(api.setStars).toHaveBeenLastCalledWith(3, { expressions: [], words: [42] })
  })

  it('puts the set back when the save fails', async () => {
    vi.mocked(api.setStars).mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual([11]))

    act(() => result.current.toggle('words', 42))
    expect(result.current.stars.words).toEqual([42])
    await waitFor(() => expect(result.current.stars.words).toEqual([]))
  })
})
