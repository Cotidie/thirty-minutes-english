import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Summary } from '../types'

/** The paragraphs summed up in a session so far, and a way to add one just kept. */
export function useSummaries(sessionId: number) {
  const [summaries, setSummaries] = useState<Summary[]>([])

  useEffect(() => {
    let live = true
    api
      .listSummaries(sessionId)
      .then((s) => live && setSummaries(s))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [sessionId])

  const add = useCallback((summary: Summary) => setSummaries((all) => [...all, summary]), [])
  return { summaries, add }
}
