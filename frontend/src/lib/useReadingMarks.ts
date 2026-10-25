import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { Shown } from './assessor/judge'
import type { Reading } from '../types'

/**
 * The marks the latest read-aloud round of each paragraph left, by paragraph id, so they stay
 * on the article from one visit to the next. Marks from before positions were kept are left out.
 */
export function useReadingMarks(sessionId: number): Map<number, Shown[]> {
  const [readings, setReadings] = useState<Reading[]>([])

  useEffect(() => {
    let live = true
    api
      .listReadings(sessionId)
      .then((r) => live && setReadings(r))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [sessionId])

  return useMemo(() => {
    const marks = new Map<number, Shown[]>()
    // Newest first, so the first reading of a paragraph is its latest.
    for (const reading of readings) {
      if (!marks.has(reading.paragraph_id)) marks.set(reading.paragraph_id, (reading.corrections ?? []).filter((c) => c.at >= 0))
    }
    return marks
  }, [readings])
}
