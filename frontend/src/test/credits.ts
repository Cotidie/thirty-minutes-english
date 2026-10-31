import type { CreditEntry } from '../types'

/** What `useCredits` gives an account with this balance and these prices, for a test that mocks it. */
export function creditsOf(balance: number | null, prices: Record<string, number> = {}, recent: CreditEntry[] = []) {
  const cost = (...kinds: string[]) => (balance === null ? 0 : kinds.reduce((sum, kind) => sum + (prices[kind] ?? 0), 0))
  return { balance, prices, recent, cost, canAfford: (...kinds: string[]) => balance === null || balance >= cost(...kinds) }
}
