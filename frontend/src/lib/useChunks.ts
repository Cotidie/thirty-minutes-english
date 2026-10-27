import { useEffect, useState } from 'react'

/** How near the bottom of the viewport the sentinel gets before the next chunk is drawn. */
const AHEAD = '0px 0px 800px 0px'

/**
 * The first `step` of `items`, and `step` more each time the element given to `sentinel` comes near the
 * viewport. A new `key` (a new search or filter) starts over at `step`; an item going (a delete) keeps the place.
 */
export function useChunks<T>(items: T[], key: string, step = 50) {
  const [drawn, setDrawn] = useState({ key, count: step })
  const [sentinel, setSentinel] = useState<Element | null>(null)
  const count = drawn.key === key ? drawn.count : step
  const more = count < items.length

  useEffect(() => {
    if (!sentinel || !more) return
    // A fresh observer reports at once, so a sentinel still in reach after a chunk draws the next one.
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setDrawn({ key, count: count + step })
      },
      { rootMargin: AHEAD },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [sentinel, more, key, count, step])

  return { shown: items.slice(0, count), more, sentinel: setSentinel }
}
