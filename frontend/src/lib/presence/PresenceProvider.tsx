import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { connectPresence } from './connection'
import { PresenceStore } from './store'

const PresenceContext = createContext<PresenceStore | null>(null)
const NOBODY_TO_HEAR = () => () => undefined

/** Everyone in this session, for as long as it is open. */
export function PresenceProvider({ sessionId, children }: { sessionId: number; children: ReactNode }) {
  const [store] = useState(() => new PresenceStore())
  useEffect(() => connectPresence(sessionId, store), [sessionId, store])
  return <PresenceContext.Provider value={store}>{children}</PresenceContext.Provider>
}

/** Outside a session there is none, and whatever asks keeps to itself. */
export function usePresenceStore(): PresenceStore | null {
  return useContext(PresenceContext)
}

/** Something read from the store, again whenever the store changes, rendering the caller only if the answer did. */
export function usePresenceValue<T>(read: (store: PresenceStore) => T): T | undefined {
  const store = usePresenceStore()
  return useSyncExternalStore(store ? store.subscribe : NOBODY_TO_HEAR, () => (store ? read(store) : undefined))
}
