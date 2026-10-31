import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api'
import type { CreditsView } from '../types'
import { creditsFrom, type Credits } from './creditView'
import { useAccountResource } from './sessionChanges'

const NOTHING_KNOWN: CreditsView = { balance: null, prices: {}, recent: [] }

const CreditsContext = createContext<Credits>(creditsFrom(NOTHING_KNOWN))

/** What the account has to spend, kept fresh for every button under it. */
export function CreditsProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState(NOTHING_KNOWN)
  useAccountResource('credits', api.myCredits, setView)
  const credits = useMemo(() => creditsFrom(view), [view])
  return <CreditsContext.Provider value={credits}>{children}</CreditsContext.Provider>
}

/** Until the balance is known, or for an account without one, nothing is short: there is no ground to stop anyone. */
export function useCredits(): Credits {
  return useContext(CreditsContext)
}

/** The same sentence a 402 carries, for a button that will not get that far. */
export function notEnough(need: number, have: number): string {
  return `Not enough credits: this needs ${need} and you have ${have}.`
}
