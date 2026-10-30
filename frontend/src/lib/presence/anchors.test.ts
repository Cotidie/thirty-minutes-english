import { afterEach, expect, test, vi } from 'vitest'
import { anchorAt, pointFor } from './anchors'

function anchored(name: string, rect: Partial<DOMRect>) {
  const element = document.createElement('div')
  element.setAttribute('data-presence-anchor', name)
  element.getBoundingClientRect = () => rect as DOMRect
  document.body.append(element)
  return element
}

afterEach(() => {
  document.body.replaceChildren()
  document.elementFromPoint = () => null
})

test('turns a point into the nearest anchor and its fractions', () => {
  const word = anchored('word:2', { left: 100, top: 200, width: 400, height: 100 })
  const inside = document.createElement('span')
  word.append(inside)
  document.elementFromPoint = vi.fn(() => inside)
  expect(anchorAt(300, 250)).toEqual({ anchor: 'word:2', x: 0.5, y: 0.5 })
})

test('nothing under the mouse carries an anchor: no cursor', () => {
  document.elementFromPoint = vi.fn(() => document.body)
  expect(anchorAt(1, 1)).toBeNull()
})

test('nothing under the mouse at all: no cursor', () => {
  document.elementFromPoint = vi.fn(() => null)
  expect(anchorAt(1, 1)).toBeNull()
})

test('a point on the very edge stays within 0 and 1', () => {
  const word = anchored('word:2', { left: 100, top: 200, width: 400, height: 100 })
  document.elementFromPoint = vi.fn(() => word)
  expect(anchorAt(99, 301)).toEqual({ anchor: 'word:2', x: 0, y: 1 })
})

test('an anchor with no size gives no fractions', () => {
  const word = anchored('word:2', { left: 100, top: 200, width: 0, height: 0 })
  document.elementFromPoint = vi.fn(() => word)
  expect(anchorAt(100, 200)).toBeNull()
})

test('turns fractions back into a point', () => {
  anchored('word:2', { left: 100, top: 200, width: 400, height: 100 })
  expect(pointFor('word:2', 0.5, 0.5)).toEqual({ left: 300, top: 250 })
})

test('an anchor not on this screen has no point', () => {
  expect(pointFor('word:999', 0.5, 0.5)).toBeNull()
})

test('an anchor with no size on this screen has no point', () => {
  anchored('word:2', { left: 0, top: 0, width: 0, height: 0 })
  expect(pointFor('word:2', 0.5, 0.5)).toBeNull()
})
