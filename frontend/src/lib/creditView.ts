import type { CreditsView } from '../types'

export interface Credits extends CreditsView {
  /** What the features named cost together. Whoever has no balance, the admin, is charged nothing. */
  cost: (...kinds: string[]) => number
  canAfford: (...kinds: string[]) => boolean
}

export function creditsFrom(view: CreditsView): Credits {
  const { balance, prices } = view
  const cost = (...kinds: string[]) => (balance === null ? 0 : kinds.reduce((sum, kind) => sum + (prices[kind] ?? 0), 0))
  return { ...view, cost, canAfford: (...kinds) => balance === null || balance >= cost(...kinds) }
}
