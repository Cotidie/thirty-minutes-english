import { useCallback, useState } from 'react'
import { api } from '../api'
import type { Summary } from '../types'
import { useSessionResource } from './sessionChanges'

/** The paragraphs summed up in a session so far, by anyone in it, and a way to add one just kept. The list read again
 * after its event may already hold the one just kept, so it is added only once. */
export function useSummaries(sessionId: number) {
  const [summaries, setSummaries] = useState<Summary[]>([])
  useSessionResource(sessionId, 'records', () => api.listSummaries(sessionId), setSummaries)

  const add = useCallback((summary: Summary) => setSummaries((all) => (all.some((s) => s.id === summary.id) ? all : [...all, summary])), [])
  return { summaries, add }
}
