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

  useSessionResource(sessionId, 'records', () => api.listReadings(sessionId), setReadings)

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
