import type { CursorPlace } from './store'

/**
 * A cursor is passed on as the element under it and the fractions of the way across it, so it points at the same thing on
 * a window of another size. The same element carries the same `data-presence-anchor` on every screen.
 */
const ANCHOR = 'data-presence-anchor'
const ROUND = 10000

function fraction(part: number, whole: number): number {
  return Math.round(Math.min(1, Math.max(0, part / whole)) * ROUND) / ROUND
}

function hasSize(rect: DOMRect): boolean {
  return rect.width > 0 && rect.height > 0
}

export function anchorAt(clientX: number, clientY: number): CursorPlace | null {
  const element = document.elementFromPoint(clientX, clientY)?.closest(`[${ANCHOR}]`)
  const anchor = element?.getAttribute(ANCHOR)
  if (!element || !anchor) return null
  const rect = element.getBoundingClientRect()
  if (!hasSize(rect)) return null
  return { anchor, x: fraction(clientX - rect.left, rect.width), y: fraction(clientY - rect.top, rect.height) }
}

export function pointFor(anchor: string, x: number, y: number): { left: number; top: number } | null {
  const rect = document.querySelector(`[${ANCHOR}="${anchor}"]`)?.getBoundingClientRect()
  if (!rect || !hasSize(rect)) return null
  return { left: rect.left + x * rect.width, top: rect.top + y * rect.height }
}
