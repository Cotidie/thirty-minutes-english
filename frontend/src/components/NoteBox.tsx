import { useCallback, useEffect, useState } from 'react'
import type { NoteStatus, SessionNote } from '../lib/useNote'
import './NoteBox.css'

const STATUS: Record<NoteStatus, string> = {
  saved: 'Saved',
  saving: 'Saving…',
  failed: 'Not saved. Type to retry.',
}

/**
 * The session's notepad: a round button beside the gear, on every tab. A click
 * or `n` opens the panel on a fresh line at the end of the note, so the next
 * thought goes straight in; Esc or `n` closes it and drops the line if it stayed empty.
 */
export function NoteBox({ note }: { note: SessionNote }) {
  const [open, setOpen] = useState(false)

  const toggle = () => {
    if (open) {
      const kept = note.text.trimEnd()
      if (kept !== note.text) note.edit(kept)
    } else if (note.text.trim() && !note.text.endsWith('\n')) {
      note.edit(`${note.text}\n`)
    }
    setOpen(!open)
  }

  // Registered anew each render, so the keys act on the note as it now reads.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if ((e.key === 'n' && !isTyping(e.target)) || (e.key === 'Escape' && open)) {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  /** The panel just opened: the caret goes to the end of the note. */
  const atEnd = useCallback((box: HTMLTextAreaElement | null) => {
    if (!box) return
    box.focus()
    box.setSelectionRange(box.value.length, box.value.length)
    box.scrollTop = box.scrollHeight
  }, [])

  return (
    <>
      <button
        type="button"
        className={`note-open${open ? ' is-open' : ''}`}
        onClick={toggle}
        aria-label={open ? 'Close notes' : 'Open notes'}
        aria-expanded={open}
        title="Notes (n)"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Zm9.5-13.5 4 4"
          />
        </svg>
        {note.text.trim() && <span className="note-dot" />}
      </button>
      {open && (
        <section className="note">
          <header className="note-head">
            <label className="note-label" htmlFor="session-note">
              Notes
            </label>
            <kbd>n</kbd>
          </header>
          <textarea
            id="session-note"
            ref={atEnd}
            className="note-text"
            value={note.text}
            onChange={(e) => note.edit(e.target.value)}
            onBlur={note.flush}
            placeholder="Anything to come back to"
          />
          <p className={`note-status is-${note.status}`} aria-live="polite">
            {STATUS[note.status]}
          </p>
        </section>
      )}
    </>
  )
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
