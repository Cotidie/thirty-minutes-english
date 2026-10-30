import { useState, useSyncExternalStore } from 'react'
import { usePresenceStore } from './PresenceProvider'
import type { ViewValue } from './store'

const NOBODY_TO_HEAR = () => () => undefined

/** `useState` for something on screen that everyone in the session sees the same: what one turns over turns over for all.
 * Only a change to this key renders the caller. */
export function useSharedView<T extends ViewValue>(key: string, initial: T): [T, (value: T) => void] {
  const store = usePresenceStore()
  const [alone, setAlone] = useState(initial)
  const shared = useSyncExternalStore(store ? store.subscribe : NOBODY_TO_HEAR, () => store?.viewValue(key))
  if (!store) return [alone, setAlone]
  return [(shared === undefined ? initial : shared) as T, (value) => store.setView(key, value)]
}
