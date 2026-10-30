import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useSessionResource } from './sessionChanges'

export type NoteStatus = 'saved' | 'saving' | 'failed'

/** How long typing must pause before the note goes to the server. */
const SAVE_DELAY_MS = 700

type Write = (text: string, keepalive: boolean) => Promise<unknown>

/**
 * What the box shows against what the server has. Saves the whole text once
 * typing pauses, one write at a time; text typed while a write is on the wire
 * goes out when it lands.
 */
class NoteSaver {
  private shown = ''
  private stored = ''
  private inFlight = false
  /** How many writes have begun, so a read begun before one can tell it is out of date. */
  writes = 0
  private timer: ReturnType<typeof setTimeout> | undefined
  private readonly write: Write
  private readonly onStatus: (status: NoteStatus) => void

  constructor(write: Write, onStatus: (status: NoteStatus) => void) {
    this.write = write
    this.onStatus = onStatus
  }

  /** The server's copy arrived, maybe someone else's. It shows only if all that was typed here is saved. */
  loaded(text: string): boolean {
    if (this.inFlight || this.shown !== this.stored) return false
    this.shown = this.stored = text
    return true
  }

  edit(text: string) {
    this.shown = text
    this.onStatus('saving')
    clearTimeout(this.timer)
    this.timer = setTimeout(() => void this.flush(), SAVE_DELAY_MS)
  }

  /** Saves now. `keepalive` lets the request finish after the page closes. */
  async flush(keepalive = false): Promise<void> {
    clearTimeout(this.timer)
    if (this.inFlight) return
    if (this.shown === this.stored) return this.onStatus('saved')
    const text = this.shown
    this.inFlight = true
    this.writes += 1
    this.onStatus('saving')
    try {
      await this.write(text, keepalive)
      this.stored = text
    } catch {
      return this.onStatus('failed')
    } finally {
      this.inFlight = false
    }
    await this.flush()
  }
}

/** A session's free-form note, saved as the pair types. */
export function useNote(sessionId: number) {
  const [text, setText] = useState('')
  const [status, setStatus] = useState<NoteStatus>('saved')
  const saver = useRef<NoteSaver | null>(null)

  useEffect(() => {
    const s = new NoteSaver((t, keepalive) => api.setNote(sessionId, t, keepalive), setStatus)
    saver.current = s
    const leave = () => void s.flush(true)
    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      void s.flush()
    }
  }, [sessionId])

  useSessionResource(
    sessionId,
    'note',
    () => {
      const begunAt = saver.current?.writes
      return api.getNote(sessionId).then((note) => ({ note, begunAt }))
    },
    ({ note, begunAt }) => {
      const s = saver.current
      if (s && begunAt === s.writes && s.loaded(note.text)) setText(note.text)
    },
  )

  const edit = useCallback((t: string) => {
    setText(t)
    saver.current?.edit(t)
  }, [])
  const flush = useCallback(() => void saver.current?.flush(), [])

  return { text, status, edit, flush }
}

export type SessionNote = ReturnType<typeof useNote>
