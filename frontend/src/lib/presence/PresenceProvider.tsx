import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { connectPresence } from './connection'
import { PresenceStore } from './store'

const PresenceContext = createContext<PresenceStore | null>(null)

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
