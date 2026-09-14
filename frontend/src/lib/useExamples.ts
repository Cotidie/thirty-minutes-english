import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Example } from '../types'

/** The sentences made in a session so far, and a way to add one just kept. */
export function useExamples(sessionId: number) {
  const [examples, setExamples] = useState<Example[]>([])

  useEffect(() => {
    let live = true
    api
      .listExamples(sessionId)
      .then((e) => live && setExamples(e))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [sessionId])

  const add = useCallback((example: Example) => setExamples((all) => [...all, example]), [])
  return { examples, add }
}
