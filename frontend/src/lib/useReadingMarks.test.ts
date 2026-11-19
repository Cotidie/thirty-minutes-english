import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Reading } from '../types'
import { useReadingMarks } from './useReadingMarks'

let show: (readings: Reading[]) => void = () => undefined
vi.mock('./sessionChanges', () => ({
  useSessionResource: (_session: number, _change: string, _read: () => unknown, apply: (readings: Reading[]) => void) => {
    show = apply
    return () => undefined
  },
}))
vi.mock('../api', () => ({ api: { listReadings: vi.fn() } }))

const reading = (id: number): Reading => ({
  id,
  created_at: '',
  paragraph_id: 4,
  user_text: 'it was not flawed',
  seconds: 3,
  corrections: [{ word: 'flawed', heard: 'flowed', fix: 'flɔːd', at: 3, score: 40, sounds: [], repeated_ok: false }],
})

it('keeps the same marks when the records come back with no new reading', () => {
  const { result } = renderHook(() => useReadingMarks(1))
  act(() => show([reading(2), reading(1)]))
  const first = result.current.marks.get(4)
  act(() => show([reading(2), reading(1)])) // a summary's feedback came in: the readings are read again, unchanged
  expect(result.current.marks.get(4)).toBe(first)
  act(() => show([reading(3), reading(2), reading(1)]))
  expect(result.current.marks.get(4)).not.toBe(first)
})
