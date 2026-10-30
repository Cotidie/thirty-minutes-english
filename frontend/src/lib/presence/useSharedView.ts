import { useState } from 'react'
import { usePresenceStore, usePresenceValue } from './PresenceProvider'
import type { ViewValue } from './store'

/** `useState` for something on screen that everyone in the session sees the same: what one turns over turns over for all.
 * Only a change to this key renders the caller. */
export function useSharedView<T extends ViewValue>(key: string, initial: T): [T, (value: T) => void] {
  const store = usePresenceStore()
  const [alone, setAlone] = useState(initial)
  const shared = usePresenceValue((s) => s.viewValue(key))
  if (!store) return [alone, setAlone]
  return [(shared === undefined ? initial : shared) as T, (value) => store.setView(key, value)]
}
