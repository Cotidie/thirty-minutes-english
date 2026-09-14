import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Example } from '../types'
import { useExamples } from './useExamples'

vi.mock('../api', () => ({ api: { listExamples: vi.fn() } }))

const one: Example = { id: 1, created_at: '', session_id: 3, expression: 'x', user_text: 'a', coach_text: 'b', seconds: 1 }

describe('useExamples', () => {
  it('loads the session list and appends what is kept afterwards', async () => {
    vi.mocked(api.listExamples).mockResolvedValue([one])
    const { result } = renderHook(() => useExamples(3))
    await waitFor(() => expect(result.current.examples).toEqual([one]))
    expect(api.listExamples).toHaveBeenCalledWith(3)

    act(() => result.current.add({ ...one, id: 2 }))
    expect(result.current.examples.map((e) => e.id)).toEqual([1, 2])
  })
})
