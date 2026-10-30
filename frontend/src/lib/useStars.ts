import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Stars } from '../types'

export type StarKind = keyof Stars

const NONE: Stars = { expressions: [], words: [] }

/**
 * A session's stars, flipped on the spot and saved one item at a time, so two people
 * starring at once keep each other's. The answer to the last save in flight is what
 * shows; a failed save puts the set back the way the server last had it.
 */
export function useStars(sessionId: number) {
  const [stars, setStars] = useState<Stars>(NONE)
  const current = useRef<Stars>(NONE)
  const saved = useRef<Stars>(NONE)
  const saving = useRef(0)

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
    (kind: StarKind, item: number) => {
      const list = current.current[kind]
      const starred = !list.includes(item)
      show({ ...current.current, [kind]: starred ? [...list, item] : list.filter((x) => x !== item) })
      saving.current += 1
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
