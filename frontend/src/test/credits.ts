import { creditsFrom } from '../lib/creditView'
import type { CreditEntry } from '../types'

/** What `useCredits` gives an account with this balance and these prices, for a test that mocks it. */
export function creditsOf(balance: number | null, prices: Record<string, number> = {}, recent: CreditEntry[] = []) {
  return creditsFrom({ balance, prices, recent })
}
