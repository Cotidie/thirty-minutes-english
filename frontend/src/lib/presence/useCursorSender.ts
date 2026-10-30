import { useEffect } from 'react'
import { anchorAt } from './anchors'
import { usePresenceStore } from './PresenceProvider'
import type { PresenceStore } from './store'

const SEND_EVERY_MS = 50

/** Watches a mouse, not a finger: a tap on a phone is no cursor. Returns how to stop. */
function watchMouse(store: PresenceStore, tab: number): () => void {
  let mouse: { x: number; y: number } | null = null
  let pending: ReturnType<typeof setTimeout> | undefined
  let lastSentAt = -Infinity
  let saidNone = false

  const sendPlace = () => {
    pending = undefined
    lastSentAt = Date.now()
    const place = mouse && anchorAt(mouse.x, mouse.y)
    if (!place && saidNone) return
    saidNone = !place
    store.sendCursor(tab, place)
  }
  const sendSoon = () => {
    if (pending !== undefined) return
    const wait = lastSentAt + SEND_EVERY_MS - Date.now()
    if (wait <= 0) sendPlace()
    else pending = setTimeout(sendPlace, wait)
  }
  const onMove = (event: PointerEvent) => {
    if (event.pointerType !== 'mouse') return
    mouse = { x: event.clientX, y: event.clientY }
    sendSoon()
  }
  const onScroll = () => {
    if (mouse) sendSoon()
  }
  const onMouseGone = () => {
    clearTimeout(pending)
    mouse = null
    sendPlace()
  }
  const onVisibility = () => {
    if (document.visibilityState === 'hidden') onMouseGone()
  }

  window.addEventListener('pointermove', onMove, { passive: true })
  window.addEventListener('scroll', onScroll, { capture: true, passive: true })
  document.documentElement.addEventListener('pointerleave', onMouseGone)
  document.addEventListener('visibilitychange', onVisibility)
  return () => {
    clearTimeout(pending)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('scroll', onScroll, { capture: true })
    document.documentElement.removeEventListener('pointerleave', onMouseGone)
    document.removeEventListener('visibilitychange', onVisibility)
  }
}

/** Tells the others where my mouse is, about 20 times a second at most. */
export function useCursorSender(tab: number): void {
  const store = usePresenceStore()
  useEffect(() => (store ? watchMouse(store, tab) : undefined), [store, tab])
}
