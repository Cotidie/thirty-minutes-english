import { useCallback, useMemo, useState } from 'react'
import { api } from '../api'
import type { Shown } from './assessor/judge'
import type { Reading } from '../types'
import { useSessionResource } from './sessionChanges'

/**
 * The marks the latest read-aloud round of each paragraph left, by paragraph id, so they stay
 * on the article from one visit to the next. Marks from before positions were kept are left out. A round just filed on
 * this page can be added before the list is read again.
 */
export function useReadingMarks(sessionId: number): { marks: Map<number, Shown[]>; add: (reading: Reading) => void } {
  const [readings, setReadings] = useState<Reading[]>([])

  // Summaries share the `records` event, so the readings often come back unchanged; keeping the list then keeps every
  // paragraph's marks the same, which is what a paragraph holding a finished round's marks waits on.
  const show = useCallback((next: Reading[]) => setReadings((now) => (sameReadings(now, next) ? now : next)), [])
  useSessionResource(sessionId, 'records', () => api.listReadings(sessionId), show)

  const add = useCallback((reading: Reading) => setReadings((all) => [reading, ...all]), [])
  const marks = useMemo(() => {
    const marks = new Map<number, Shown[]>()
    // Newest first, so the first reading of a paragraph is its latest.
    for (const reading of readings) {
      if (!marks.has(reading.paragraph_id)) marks.set(reading.paragraph_id, (reading.corrections ?? []).filter((c) => c.at >= 0))
    }
    return marks
  }, [readings])
  return { marks, add }
}

/** Readings are never changed once filed, so the same ids in the same order with the same marks are the same list. */
function sameReadings(a: Reading[], b: Reading[]): boolean {
  return a.length === b.length && a.every((r, i) => r.id === b[i].id && JSON.stringify(r.corrections) === JSON.stringify(b[i].corrections))
}
