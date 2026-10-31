import { notEnough, useCredits } from './credits'

/** What pressing a button for these features costs this account, and why it cannot pay, when it cannot. */
export function usePrice(...kinds: string[]): { price: number; short: string | null } {
  const { balance, cost, canAfford } = useCredits()
  const price = cost(...kinds)
  return { price, short: canAfford(...kinds) ? null : notEnough(price, balance ?? 0) }
}
