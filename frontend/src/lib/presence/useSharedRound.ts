import { useCallback } from 'react'
import { usePresenceStore, usePresenceValue } from './PresenceProvider'
import type { OthersRound, SharedRound } from './store'

const SOMEONE = 'Someone'

/** Tells the others in the session about my read-aloud round; outside a session, no one. The same function for as long
 * as the session is open. */
export function useShareRound(): (round: SharedRound | null) => void {
  const store = usePresenceStore()
  return useCallback((round: SharedRound | null) => store?.setRound(round), [store])
}

/** Someone else's round on this paragraph, with the name and color of whoever reads it. */
export function useOthersRound(paragraphId: number): { round: OthersRound; name: string; color: number } | null {
  const round = usePresenceValue((store) => store.roundOn(paragraphId))
  const person = usePresenceValue((store) => (round ? store.person(round.by) : undefined))
  if (!round) return null
  return { round, name: person?.name ?? SOMEONE, color: person?.color ?? 0 }
}

/** The name of whoever else is reading aloud right now, anywhere in the article. */
export function useSomeoneReading(): string | null {
  const round = usePresenceValue((store) => store.reading())
  const person = usePresenceValue((store) => (round ? store.person(round.by) : undefined))
  if (!round) return null
  return person?.name ?? SOMEONE
}
