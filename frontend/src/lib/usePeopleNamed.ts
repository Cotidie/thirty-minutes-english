import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PersonMatch } from '../types'

const PAUSE_MS = 150

export interface PeopleNamed {
  /** The last answer that came, which may be for text typed a moment ago: the list keeps still while typing goes on. */
  people: PersonMatch[]
  /** Whether `people` answers this very text. */
  settled: boolean
  /** Whether the search for this very text failed. */
  failed: boolean
}

const BLANK: PeopleNamed = { people: [], settled: true, failed: false }

/** The accounts whose username holds `text`, asked for once typing pauses. A late answer for older text is dropped. */
export function usePeopleNamed(text: string): PeopleNamed {
  const [answer, setAnswer] = useState<{ text: string; people: PersonMatch[] } | null>(null)
  const [failedText, setFailedText] = useState<string | null>(null)
  const needle = text.trim()

  useEffect(() => {
    if (!needle) return
    let live = true
    const timer = setTimeout(() => {
      api.findPeople(needle).then(
        (people) => {
          if (!live) return
          setAnswer({ text: needle, people })
          setFailedText(null)
        },
        () => live && setFailedText(needle),
      )
    }, PAUSE_MS)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [needle])

  if (!needle) return BLANK
  return { people: answer?.people ?? [], settled: answer?.text === needle, failed: failedText === needle }
}

/** What a search that lists nobody says. */
export function nobodySaying(found: PeopleNamed): string {
  if (found.settled) return 'No one goes by a name like that.'
  return found.failed ? 'The search did not go through. Type again to retry.' : 'Looking…'
}
