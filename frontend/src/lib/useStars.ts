import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Stars } from '../types'

export type StarKind = keyof Stars

const NONE: Stars = { expressions: [], words: [] }

/**
 * A session's stars, flipped on the spot and saved as a whole set. A failed
 * save puts the set back the way the server last had it.
 */
export function useStars(sessionId: number) {
  const [stars, setStars] = useState<Stars>(NONE)
  const current = useRef<Stars>(NONE)
  const saved = useRef<Stars>(NONE)

  const show = (s: Stars) => {
    current.current = s
    setStars(s)
  }

  useEffect(() => {
    let live = true
    api
      .getStars(sessionId)
      .then((s) => {
        if (!live) return
        saved.current = s
        show(s)
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [sessionId])

  const toggle = useCallback(
    (kind: StarKind, item: string) => {
      const list = current.current[kind]
      const next = { ...current.current, [kind]: list.includes(item) ? list.filter((x) => x !== item) : [...list, item] }
      show(next)
      api
        .setStars(sessionId, next)
        .then((s) => {
          saved.current = s
        })
        .catch(() => show(saved.current))
    },
    [sessionId],
  )

  return { stars, toggle }
}
