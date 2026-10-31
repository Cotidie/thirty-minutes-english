import { expect, test, vi } from 'vitest'
import { PresenceStore, type ServerMessage } from './store'

const WELCOME = { type: 'welcome', you: { id: 'me', color: 0 }, people: [], view: {}, timer: null } as const

function joined(id: string) {
  const sent: Record<string, unknown>[] = []
  const store = new PresenceStore()
  store.attach((message) => sent.push(message as Record<string, unknown>))
  store.receive({ ...WELCOME, you: { id, color: 0 } })
  return { store, sent }
}

test.each([
  [['a', 'b'] as const, false],
  [['b', 'a'] as const, true],
])('pressing the same chip together ends the same on both screens: server order %j', (order, final) => {
  const a = joined('a')
  const b = joined('b')
  a.store.setView('chip', true)
  b.store.setView('chip', false)
  const fromServer: Record<'a' | 'b', ServerMessage> = {
    a: { type: 'view', key: 'chip', value: true, by: 'a', seq: a.sent[0].seq as number },
    b: { type: 'view', key: 'chip', value: false, by: 'b', seq: b.sent[0].seq as number },
  }
  for (const who of order) {
    a.store.receive(fromServer[who])
    b.store.receive(fromServer[who])
  }
  expect(a.store.viewValue('chip')).toBe(final)
  expect(b.store.viewValue('chip')).toBe(final)
})

test('a value from someone else does not flicker over mine while mine is on its way', () => {
  const a = joined('a')
  a.store.setView('chip', true)
  a.store.receive({ type: 'view', key: 'chip', value: false, by: 'b', seq: 1 })
  expect(a.store.viewValue('chip')).toBe(true)
})

test('my older value coming back does not undo my newer one', () => {
  const a = joined('a')
  a.store.setView('chip', true)
  a.store.setView('chip', false)
  a.store.receive({ type: 'view', key: 'chip', value: true, by: 'a', seq: a.sent[0].seq as number })
  expect(a.store.viewValue('chip')).toBe(false)
})

test('a received value is not sent back', () => {
  const a = joined('a')
  a.store.receive({ type: 'view', key: 'chip', value: true, by: 'b', seq: 1 })
  expect(a.store.viewValue('chip')).toBe(true)
  expect(a.sent).toEqual([])
})

test('a cursor tells cursor listeners and never React listeners', () => {
  const { store } = joined('a')
  const react = vi.fn()
  const cursors = vi.fn()
  store.subscribe(react)
  store.onCursor(cursors)
  store.receive({ type: 'cursor', id: 'b', tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  expect(cursors).toHaveBeenCalledWith('b', { tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  expect(store.cursorOf('b')).toEqual({ tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  expect(react).not.toHaveBeenCalled()
})

test('a cursor that says there is none takes it away', () => {
  const { store } = joined('a')
  store.receive({ type: 'cursor', id: 'b', tab: 0, anchor: 'brief', x: 0.5, y: 0.5 })
  const cursors = vi.fn()
  store.onCursor(cursors)
  store.receive({ type: 'cursor', id: 'b', tab: 0, anchor: null })
  expect(cursors).toHaveBeenCalledWith('b', null)
  expect(store.cursorOf('b')).toBeUndefined()
})

test('people come, move between tabs and go', () => {
  const { store } = joined('a')
  store.receive({ type: 'joined', id: 'b', color: 1, tab: null })
  expect(store.people()).toEqual([{ id: 'b', color: 1, tab: null }])
  store.receive({ type: 'tab', id: 'b', tab: 2 })
  expect(store.people()).toEqual([{ id: 'b', color: 1, tab: 2 }])
  store.receive({ type: 'cursor', id: 'b', tab: 2, anchor: 'brief', x: 0, y: 0 })
  const cursors = vi.fn()
  store.onCursor(cursors)
  store.receive({ type: 'left', id: 'b' })
  expect(store.people()).toEqual([])
  expect(cursors).toHaveBeenCalledWith('b', null)
})

test('the list of people keeps its identity until it changes', () => {
  const { store } = joined('a')
  const before = store.people()
  store.receive({ type: 'view', key: 'chip', value: true, by: 'b', seq: 1 })
  expect(store.people()).toBe(before)
})

test('a welcome after a reconnect replaces everyone and forgets their cursors', () => {
  const { store } = joined('a')
  store.receive({ type: 'joined', id: 'b', color: 1, tab: 2 })
  store.receive({ type: 'cursor', id: 'b', tab: 2, anchor: 'brief', x: 0, y: 0 })
  const gone = vi.fn()
  store.onCursor(gone)
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(store.people()).toEqual([])
  expect(gone).toHaveBeenCalledWith('b', null)
})

test('a welcome replaces what is turned over and clears what I was waiting on', () => {
  const { store } = joined('a')
  store.setView('mine', true)
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 }, view: { theirs: 'ko' } })
  expect(store.viewValue('theirs')).toBe('ko')
  expect(store.viewValue('mine')).toBeUndefined()
  store.receive({ type: 'view', key: 'mine', value: false, by: 'b', seq: 1 })
  expect(store.viewValue('mine')).toBe(false)
})

test('a welcome says the tab again', () => {
  const { store, sent } = joined('a')
  store.setTab(2)
  expect(sent).toEqual([{ type: 'tab', tab: 2 }])
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([{ type: 'tab', tab: 2 }])
})

test('a welcome says where my mouse stands, after the tab', () => {
  const { store, sent } = joined('a')
  store.setTab(2)
  store.sendCursor(2, { anchor: 'brief', x: 0.2, y: 0.3 })
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([
    { type: 'tab', tab: 2 },
    { type: 'cursor', tab: 2, anchor: 'brief', x: 0.2, y: 0.3 },
  ])
})

test('a welcome says nothing of a cursor that has gone', () => {
  const { store, sent } = joined('a')
  store.sendCursor(2, { anchor: 'brief', x: 0.2, y: 0.3 })
  store.sendCursor(2, null)
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([])
})

test('a restarted server gets a running timer back, but not an untouched one', () => {
  const { store, sent } = joined('a')
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 } })
  expect(sent).toEqual([])
  store.setTimer(true, 60)
  sent.length = 0
  store.receive({ ...WELCOME, you: { id: 'a3', color: 0 } })
  expect(sent).toHaveLength(1)
  expect(sent[0]).toMatchObject({ type: 'timer', running: true, elapsed: 60 })
})

test('a welcome with a timer takes it over', () => {
  const { store } = joined('a')
  store.receive({ ...WELCOME, you: { id: 'a2', color: 0 }, timer: { running: true, elapsed: 600 } })
  expect(store.timer()).toMatchObject({ running: true, elapsed: 600 })
})

test('the timer waits for my own write to come back, like any other value', () => {
  const a = joined('a')
  a.store.setTimer(true, 10)
  a.store.receive({ type: 'timer', running: false, elapsed: 0, by: 'b', seq: 1 })
  expect(a.store.timer()).toMatchObject({ running: true, elapsed: 10 })
  a.store.receive({ type: 'timer', running: true, elapsed: 10, by: 'a', seq: a.sent[0].seq as number })
  a.store.receive({ type: 'timer', running: false, elapsed: 0, by: 'b', seq: 2 })
  expect(a.store.timer()).toMatchObject({ running: false, elapsed: 0 })
})

test('a cursor is sent as a place, or as none', () => {
  const { store, sent } = joined('a')
  store.sendCursor(1, { anchor: 'brief', x: 0.2, y: 0.3 })
  store.sendCursor(1, null)
  expect(sent).toEqual([
    { type: 'cursor', tab: 1, anchor: 'brief', x: 0.2, y: 0.3 },
    { type: 'cursor', tab: 1, anchor: null },
  ])
})
