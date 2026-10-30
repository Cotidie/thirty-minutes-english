import { useEffect, useRef, type RefObject } from 'react'
import { anchorAt } from './anchors'
import { usePresenceStore } from './PresenceProvider'
import type { PresenceStore } from './store'

const SEND_EVERY_MS = 50

interface Mouse {
  x: number
  y: number
}

/** Watches a mouse, not a finger: a tap on a phone is no cursor. Returns how to stop. */
function watchMouse(store: PresenceStore, tab: number, mouse: RefObject<Mouse | null>): () => void {
  let pending: ReturnType<typeof setTimeout> | undefined
  let lastSentAt = -Infinity
  let saidNone = false

  const sendPlace = () => {
    pending = undefined
    lastSentAt = Date.now()
    const place = mouse.current && anchorAt(mouse.current.x, mouse.current.y)
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
    mouse.current = { x: event.clientX, y: event.clientY }
    sendSoon()
  }
  const onScroll = () => {
    if (mouse.current) sendSoon()
  }
  const onMouseGone = () => {
    clearTimeout(pending)
    mouse.current = null
    sendPlace()
  }
  const onVisibility = () => {
    if (document.visibilityState === 'hidden') onMouseGone()
  }

  window.addEventListener('pointermove', onMove, { passive: true })
  window.addEventListener('scroll', onScroll, { capture: true, passive: true })
  document.documentElement.addEventListener('pointerleave', onMouseGone)
  document.addEventListener('visibilitychange', onVisibility)
  if (mouse.current) sendSoon() // a new tab, under a mouse standing still
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
  const mouse = useRef<Mouse | null>(null)
  useEffect(() => (store ? watchMouse(store, tab, mouse) : undefined), [store, tab])
}
