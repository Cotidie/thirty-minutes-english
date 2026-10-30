import { useEffect, useReducer, useState } from 'react'
import { SESSION_SECONDS } from '../phases'
import { usePresenceStore, usePresenceValue } from './PresenceProvider'
import { timerElapsed, type TimerValue } from './store'

const STOPPED: TimerValue = { running: false, elapsed: 0, at: 0 }

/**
 * The session's one timer, or a timer of its own with nobody to share it with. The time comes from the clock each time
 * it is read: a hidden tab's interval slows down, and that must not put this screen behind the others.
 */
export function useSharedTimer() {
  const store = usePresenceStore()
  const [alone, setAlone] = useState(STOPPED)
  const shared = usePresenceValue((s) => s.timer())
  const timer = store ? (shared ?? STOPPED) : alone
  const [, redraw] = useReducer((count: number) => count + 1, 0)

  useEffect(() => {
    if (!timer.running) return
    const id = window.setInterval(redraw, 1000)
    return () => window.clearInterval(id)
  }, [timer.running])

  const elapsed = Math.min(SESSION_SECONDS, timerElapsed(timer))
  const set = (running: boolean, seconds: number) => {
    if (store) store.setTimer(running, seconds)
    else setAlone({ running, elapsed: seconds, at: Date.now() })
  }
  return {
    elapsed,
    running: timer.running && elapsed < SESSION_SECONDS,
    start: () => set(true, elapsed),
    pause: () => set(false, elapsed),
    reset: () => set(false, 0),
  }
}
