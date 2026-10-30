import { useCallback, useRef, useState } from 'react'
import { api } from '../api'
import type { Stars } from '../types'
import { useSessionResource } from './sessionChanges'

export type StarKind = keyof Stars

const NONE: Stars = { expressions: [], words: [] }

/**
 * A session's stars, flipped on the spot and saved one item at a time, so two people
 * starring at once keep each other's. The answer to the newest save is what shows, whichever
 * lands last; a failed save puts the set back the way the server last had it. Someone else's
 * star shows when it is announced, or just after the saves in flight.
 */
export function useStars(sessionId: number) {
  const [stars, setStars] = useState<Stars>(NONE)
  const current = useRef<Stars>(NONE)
  const saved = useRef<Stars>(NONE)
  const saving = useRef(0)
  const toggles = useRef(0)
  const answered = useRef(0)
  const setAside = useRef(false)

  const show = (s: Stars) => {
    current.current = s
    setStars(s)
  }

  // While a save is in flight a read is set aside and made again after, since the save's answer may not hold
  // what someone else did. A read begun before a save that lands after it is old: that save's own announcement
  // brings a fresh one.
  const readAgain = useSessionResource(
    sessionId,
    'stars',
    () => {
      const begunAt = toggles.current
      return api.getStars(sessionId).then((read) => ({ read, begunAt }))
    },
    ({ read, begunAt }) => {
      if (saving.current > 0) {
        setAside.current = true
        return
      }
      if (begunAt !== toggles.current) return
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
      const number = toggles.current
      api
        .setStar(sessionId, kind, item, starred)
        .then((s) => {
          if (number > answered.current) {
            answered.current = number
            saved.current = s
          }
          if (number === toggles.current) show(s)
        })
        .catch(() => {
          if (number === toggles.current) show(saved.current)
        })
        .finally(() => {
          saving.current -= 1
          if (saving.current === 0 && setAside.current) {
            setAside.current = false
            readAgain()
          }
        })
    },
    [sessionId, readAgain],
  )

  return { stars, toggle }
}
