import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Topic, TopicListing } from '../types'

/** How often to look back for the day's news topics while they are still coming. */
export const TOPIC_POLL_MS = 15_000
export const TOPIC_POLL_LIMIT = 12

/**
 * Today's suggestions. The news half is fetched on the server the first time
 * anyone asks; until it lands the pool fills the list, so we keep looking for
 * a while. `refresh` deals a new list and starts that fetch again.
 */
export function useTopics() {
  const [topics, setTopics] = useState<Topic[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [labels, setLabels] = useState<Record<string, string>>({})
  const live = useRef(true)
  const tries = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopPolling = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }

  // Named so the poll it schedules can call it again.
  const take = useCallback(function take(listing: TopicListing) {
    if (!live.current) return
    setTopics(listing.topics)
    setError(listing.error)
    setLabels(listing.labels)
    // Past the limit we stop believing the server and let the button go again.
    const keepLooking = listing.pending && tries.current++ < TOPIC_POLL_LIMIT
    setPending(keepLooking)
    if (keepLooking) {
      timer.current = setTimeout(() => api.topics().then(take).catch(() => undefined), TOPIC_POLL_MS)
    }
  }, [])

  useEffect(() => {
    live.current = true
    api
      .topics()
      .then(take)
      .catch(() => live.current && setTopics([]))
    return () => {
      live.current = false
      stopPolling()
    }
  }, [take])

  const refresh = useCallback(() => {
    stopPolling()
    tries.current = 0
    setPending(true)
    api
      .refreshTopics()
      .then(take)
      .catch(() => live.current && setPending(false))
  }, [take])

  return { topics, labels, pending, error, refresh }
}
