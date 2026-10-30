import { useEffect } from 'react'
import { usePresenceStore, usePresenceValue } from './PresenceProvider'
import type { Person } from './store'

const NOBODY: readonly Person[] = []

/** The colors of the people on this tab; one for someone there on two connections. */
export function useOthersOnTab(tab: number): number[] {
  const people = usePresenceValue((store) => store.people()) ?? NOBODY
  return [...new Set(people.filter((person) => person.tab === tab).map((person) => person.color))]
}

export function useTellMyTab(tab: number): void {
  const store = usePresenceStore()
  useEffect(() => {
    store?.setTab(tab)
  }, [store, tab])
}
