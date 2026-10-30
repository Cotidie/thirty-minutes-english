import { useEffect, useRef } from 'react'
import { pointFor } from '../lib/presence/anchors'
import { usePresenceStore } from '../lib/presence/PresenceProvider'
import { personColor, type PresenceStore } from '../lib/presence/store'
import './Cursors.css'

const EDGE_PX = 8

/** Keeps the cursors in `layer` where the store says they are, straight on the DOM: they move many times a second, and
 * nothing here may render the page. Returns how to stop. */
function drawCursors(store: PresenceStore, layer: HTMLElement): () => void {
  const drawn = new Map<string, HTMLElement>()

  const remove = (id: string) => {
    drawn.get(id)?.remove()
    drawn.delete(id)
  }
  const cursorOf = (id: string) => {
    const existing = drawn.get(id)
    if (existing) return existing
    const cursor = document.createElement('div')
    cursor.className = 'cursor'
    cursor.append(Object.assign(document.createElement('span'), { className: 'cursor-arrow' }))
    layer.append(cursor)
    drawn.set(id, cursor)
    return cursor
  }
  const place = (id: string) => {
    const at = store.cursorOf(id)
    const point = at && at.tab === store.myTab() ? pointFor(at.anchor, at.x, at.y) : null
    if (!point) {
      remove(id)
      return
    }
    const color = store.people().find((person) => person.id === id)?.color ?? 0
    const cursor = cursorOf(id)
    cursor.style.setProperty('--person', personColor(color))
    cursor.classList.toggle('is-above', point.top < 0)
    cursor.classList.toggle('is-below', point.top > window.innerHeight)
    const left = Math.min(Math.max(point.left, EDGE_PX), window.innerWidth - EDGE_PX)
    const top = Math.min(Math.max(point.top, EDGE_PX), window.innerHeight - EDGE_PX)
    cursor.style.transform = `translate(${left}px, ${top}px)`
  }
  const placeAll = () => {
    ;[...drawn.keys(), ...store.cursorIds()].forEach(place)
  }

  const stopCursors = store.onCursor((id) => place(id))
  const stopChanges = store.subscribe(placeAll)
  window.addEventListener('scroll', placeAll, { capture: true, passive: true })
  window.addEventListener('resize', placeAll)
  const contentSize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(placeAll)
  contentSize?.observe(document.body)
  placeAll()
  return () => {
    stopCursors()
    stopChanges()
    window.removeEventListener('scroll', placeAll, { capture: true })
    window.removeEventListener('resize', placeAll)
    contentSize?.disconnect()
    drawn.forEach((cursor) => cursor.remove())
  }
}

/** Where the others are pointing, over the page and never in its way. */
export function Cursors() {
  const store = usePresenceStore()
  const layer = useRef<HTMLDivElement>(null)
  useEffect(() => (store && layer.current ? drawCursors(store, layer.current) : undefined), [store])
  return <div ref={layer} className="cursors" aria-hidden="true" />
}
