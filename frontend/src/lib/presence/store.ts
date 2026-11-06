/**
 * What the presence socket says: who is here and what is on their screens. It lives outside React, so a cursor,
 * which arrives many times a second, renders nothing. None of it is saved anywhere.
 */

import type { Shown } from '../assessor/judge'

export type ViewValue = boolean | number | string | null

export interface Person {
  id: string
  /** Their username as it was when they came in. */
  name: string
  color: number
  tab: number | null
}

export interface CursorPlace {
  anchor: string
  x: number
  y: number
}

export interface CursorAt extends CursorPlace {
  tab: number
}

/** `elapsed` seconds had passed at `at`, by `Date.now()`. */
export interface TimerValue {
  running: boolean
  elapsed: number
  at: number
}

/** A read-aloud round as the reader's screen has it: `reading` while they connect or read, `done` once the marks are final. */
export interface SharedRound {
  paragraph: number
  phase: 'reading' | 'done'
  /** All that was heard so far. */
  heard: string
  findings: Shown[]
}

/** Someone else's round, with the connection it came from. */
export interface OthersRound extends SharedRound {
  by: string
}

export type ServerMessage =
  | {
      type: 'welcome'
      you: { id: string; color: number }
      people: readonly Person[]
      view: Readonly<Record<string, ViewValue>>
      timer: { running: boolean; elapsed: number } | null
      rounds: Readonly<Record<string, SharedRound>>
    }
  | ({ type: 'joined' } & Person)
  | { type: 'left'; id: string }
  | { type: 'tab'; id: string; tab: number }
  | ({ type: 'cursor'; id: string; tab: number } & (CursorPlace | { anchor: null }))
  | { type: 'view'; key: string; value: ViewValue; by: string; seq: number }
  | { type: 'timer'; running: boolean; elapsed: number; by: string; seq: number }
  | { type: 'round'; id: string; round: SharedRound | null }

const TIMER_KEY = ' timer' // a space, which no view key has
const PERSON_COLORS = 6 // the --person-N tokens in base.css

export function personColor(color: number): string {
  return `var(--person-${(color % PERSON_COLORS) + 1})`
}

export function timerElapsed(timer: TimerValue, now = Date.now()): number {
  return Math.floor(timer.elapsed + (timer.running ? (now - timer.at) / 1000 : 0))
}

export class PresenceStore {
  private send: ((message: object) => void) | null = null
  private myId: string | null = null
  private view = new Map<string, ViewValue>()
  private everyone: readonly Person[] = []
  private readonly cursors = new Map<string, CursorAt>()
  private tab: number | null = null
  private myCursor: CursorAt | null = null
  private timerValue: TimerValue | null = null
  /** The others' rounds, by connection. */
  private rounds = new Map<string, OthersRound>()
  private myRound: SharedRound | null = null
  private lastSeq = 0
  /** The write of mine still on its way back, per key. */
  private readonly waiting = new Map<string, number>()
  private readonly listeners = new Set<() => void>()
  private readonly cursorListeners = new Set<(id: string, at: CursorAt | null) => void>()

  attach(send: ((message: object) => void) | null) {
    this.send = send
  }

  /** For React: never called for a cursor. */
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  onCursor(listener: (id: string, at: CursorAt | null) => void) {
    this.cursorListeners.add(listener)
    return () => {
      this.cursorListeners.delete(listener)
    }
  }

  viewValue(key: string): ViewValue | undefined {
    return this.view.get(key)
  }

  people(): readonly Person[] {
    return this.everyone
  }

  cursorOf(id: string): CursorAt | undefined {
    return this.cursors.get(id)
  }

  cursorIds(): string[] {
    return [...this.cursors.keys()]
  }

  myTab(): number | null {
    return this.tab
  }

  timer(): TimerValue | null {
    return this.timerValue
  }

  /** Someone else's round on this paragraph. */
  roundOn(paragraph: number): OthersRound | undefined {
    return [...this.rounds.values()].findLast((round) => round.paragraph === paragraph)
  }

  /** Someone else's round still being read, wherever it is. */
  reading(): OthersRound | undefined {
    return [...this.rounds.values()].find((round) => round.phase === 'reading')
  }

  person(id: string): Person | undefined {
    return this.everyone.find((person) => person.id === id)
  }

  setView(key: string, value: ViewValue) {
    this.view.set(key, value)
    this.send?.({ type: 'view', key, value, seq: this.nextSeq(key) })
    this.changed()
  }

  setTab(tab: number) {
    this.tab = tab
    this.send?.({ type: 'tab', tab })
    this.changed()
  }

  setTimer(running: boolean, elapsed: number) {
    this.timerValue = { running, elapsed, at: Date.now() }
    this.sendTimer()
    this.changed()
  }

  /** My round goes to the others; none of mine is read back from here. */
  setRound(round: SharedRound | null) {
    this.myRound = round
    this.send?.({ type: 'round', round })
  }

  sendCursor(tab: number, place: CursorPlace | null) {
    this.myCursor = place && { tab, ...place }
    this.send?.({ type: 'cursor', tab, ...(place ?? { anchor: null }) })
  }

  receive(message: ServerMessage) {
    switch (message.type) {
      case 'welcome':
        this.startOver(message)
        break
      case 'joined':
        this.everyone = [...this.everyone, { id: message.id, name: message.name, color: message.color, tab: message.tab }]
        this.changed()
        break
      case 'left':
        this.everyone = this.everyone.filter((person) => person.id !== message.id)
        this.rounds.delete(message.id)
        this.placeCursor(message.id, null)
        this.changed()
        break
      case 'tab':
        this.everyone = this.everyone.map((person) => (person.id === message.id ? { ...person, tab: message.tab } : person))
        this.changed()
        break
      case 'cursor':
        this.placeCursor(
          message.id,
          message.anchor === null ? null : { tab: message.tab, anchor: message.anchor, x: message.x, y: message.y },
        )
        break
      case 'view':
        if (this.takesIt(message.key, message)) {
          this.view.set(message.key, message.value)
          this.changed()
        }
        break
      case 'timer':
        if (this.takesIt(TIMER_KEY, message)) {
          this.timerValue = { running: message.running, elapsed: message.elapsed, at: Date.now() }
          this.changed()
        }
        break
      case 'round':
        if (message.round === null) this.rounds.delete(message.id)
        else this.rounds.set(message.id, { ...message.round, by: message.id })
        this.changed()
        break
    }
  }

  /** The server sends every write to everyone in the order it got them, so taking them in that order ends on the same
   * value everywhere. While a write of mine is on its way it will land after what arrives now, so that is skipped. */
  private takesIt(key: string, write: { by: string; seq: number }): boolean {
    const mine = this.waiting.get(key)
    if (mine === undefined) return true
    if (write.by !== this.myId || write.seq !== mine) return false
    this.waiting.delete(key)
    return true
  }

  private startOver(welcome: Extract<ServerMessage, { type: 'welcome' }>) {
    this.myId = welcome.you.id
    this.waiting.clear()
    this.view = new Map(Object.entries(welcome.view))
    this.everyone = welcome.people
    this.rounds = new Map(Object.entries(welcome.rounds).map(([id, round]) => [id, { ...round, by: id }]))
    this.cursorIds().forEach((id) => this.placeCursor(id, null))
    if (this.tab !== null) this.send?.({ type: 'tab', tab: this.tab })
    if (this.myCursor !== null) this.send?.({ type: 'cursor', ...this.myCursor })
    if (this.myRound !== null) this.send?.({ type: 'round', round: this.myRound })
    if (welcome.timer !== null) {
      this.timerValue = { ...welcome.timer, at: Date.now() }
    } else if (this.timerValue !== null && timerElapsed(this.timerValue) > 0) {
      this.timerValue = { ...this.timerValue, elapsed: timerElapsed(this.timerValue), at: Date.now() }
      this.sendTimer()
    }
    this.changed()
  }

  private sendTimer() {
    if (this.timerValue === null) return
    const { running, elapsed } = this.timerValue
    this.send?.({ type: 'timer', running, elapsed, seq: this.nextSeq(TIMER_KEY) })
  }

  private placeCursor(id: string, at: CursorAt | null) {
    if (at === null) this.cursors.delete(id)
    else this.cursors.set(id, at)
    this.cursorListeners.forEach((listener) => listener(id, at))
  }

  private nextSeq(key: string): number {
    this.lastSeq += 1
    this.waiting.set(key, this.lastSeq)
    return this.lastSeq
  }

  private changed() {
    this.listeners.forEach((listener) => listener())
  }
}
