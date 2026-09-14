import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { useStars } from './useStars'

vi.mock('../api', () => ({ api: { getStars: vi.fn(), setStars: vi.fn() } }))

beforeEach(() => {
  vi.mocked(api.getStars).mockResolvedValue({ expressions: ['on the fence'], words: [] })
  vi.mocked(api.setStars).mockImplementation(async (_id, stars) => stars)
})

describe('useStars', () => {
  it('loads the saved set, then flips an item and saves the whole set', async () => {
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual(['on the fence']))

    act(() => result.current.toggle('words', 'mitigate'))
    expect(result.current.stars.words).toEqual(['mitigate'])
    expect(api.setStars).toHaveBeenLastCalledWith(3, { expressions: ['on the fence'], words: ['mitigate'] })

    act(() => result.current.toggle('expressions', 'on the fence'))
    expect(api.setStars).toHaveBeenLastCalledWith(3, { expressions: [], words: ['mitigate'] })
  })

  it('puts the set back when the save fails', async () => {
    vi.mocked(api.setStars).mockRejectedValueOnce(new Error('offline'))
    const { result } = renderHook(() => useStars(3))
    await waitFor(() => expect(result.current.stars.expressions).toEqual(['on the fence']))

    act(() => result.current.toggle('words', 'mitigate'))
    expect(result.current.stars.words).toEqual(['mitigate'])
    await waitFor(() => expect(result.current.stars.words).toEqual([]))
  })
})
