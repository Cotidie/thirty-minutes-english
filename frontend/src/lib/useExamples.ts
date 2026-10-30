import { useCallback, useState } from 'react'
import { api } from '../api'
import type { Example } from '../types'
import { useSessionResource } from './sessionChanges'

/** The sentences made in a session so far, by anyone in it, and a way to add one just kept. */
export function useExamples(sessionId: number) {
  const [examples, setExamples] = useState<Example[]>([])
  useSessionResource(sessionId, 'records', () => api.listExamples(sessionId), setExamples)

  const add = useCallback((example: Example) => setExamples((all) => [...all, example]), [])
  return { examples, add }
}
