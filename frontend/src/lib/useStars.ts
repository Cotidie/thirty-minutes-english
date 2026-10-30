import { useCallback, useRef, useState } from 'react'
import { api } from '../api'
import type { Stars } from '../types'
import { useSessionResource } from './sessionChanges'

export type StarKind = keyof Stars

const NONE: Stars = { expressions: [], words: [] }

/**
 * A session's stars, flipped on the spot and saved one item at a time, so two people
 * starring at once keep each other's. The answer to the last save in flight is what
 * shows; a failed save puts the set back the way the server last had it. Someone else's
 * star shows when it is announced, unless a save of mine is in flight: its answer is newer.
 */
export function useStars(sessionId: number) {
  const [stars, setStars] = useState<Stars>(NONE)
  const current = useRef<Stars>(NONE)
  const saved = useRef<Stars>(NONE)
  const saving = useRef(0)
  const toggles = useRef(0)

  const show = (s: Stars) => {
    current.current = s
    setStars(s)
  }

  // A read begun before a save may land after it, so it counts only if nothing was toggled since it began.
  useSessionResource(
    sessionId,
    'stars',
    () => {
      const begunAt = toggles.current
      return api.getStars(sessionId).then((read) => ({ read, begunAt }))
    },
    ({ read, begunAt }) => {
      if (saving.current > 0 || begunAt !== toggles.current) return
      saved.current = read
      show(read)
    },
  )

  const toggle = useCallback(
    (kind: StarKind, item: number) => {
      const list = current.current[kind]
      const starred = !list.includes(item)
      show({ ...current.current, [kind]: starred ? [...list, item] : list.filter((x) => x !== item) })
      saving.current += 1
      toggles.current += 1
      api
        .setStar(sessionId, kind, item, starred)
        .then((s) => {
          saved.current = s
          if (saving.current === 1) show(s)
        })
        .catch(() => {
          if (saving.current === 1) show(saved.current)
        })
        .finally(() => {
          saving.current -= 1
        })
    },
    [sessionId],
  )

  return { stars, toggle }
}
