import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import { useStars } from './useStars'

vi.mock('../api', () => ({ api: { getStars: vi.fn(), setStar: vi.fn() } }))

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
})
