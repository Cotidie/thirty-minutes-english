// PROTOTYPE, throwaway. Three layouts for the session notes, switchable via
// `?variant=A|B|C` on the existing /s/:id route. Pick one, then rebuild it
// properly with tests and delete this folder.
import { useEffect, useState } from 'react'
import type { SessionNote } from '../../lib/useNote'
import { PrototypeSwitcher } from './PrototypeSwitcher'
import './NotesVariants.css'

const STATUS = { saved: 'Saved', saving: 'Saving…', failed: 'Not saved. Type to retry.' } as const

const VARIANTS = [
  { key: 'A', name: 'Button + panel (like Settings)' },
  { key: 'B', name: 'Margin column' },
  { key: 'C', name: 'Quick-jot bar' },
]

export function NotesPrototype({ note, variant }: { note: SessionNote; variant: string }) {
  const current = VARIANTS.some((v) => v.key === variant) ? variant : 'A'
  return (
    <>
      {current === 'A' && <VariantA note={note} />}
      {current === 'B' && <VariantB note={note} />}
      {current === 'C' && <VariantC note={note} />}
      {import.meta.env.DEV && <PrototypeSwitcher variants={VARIANTS} current={current} />}
    </>
  )
}

function Pencil() {
  return (
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
  )
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/** A: a round button beside the gear. Click or `n` opens a floating panel; Esc or `n` again closes it. */
function VariantA({ note }: { note: SessionNote }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'n') {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <button
        type="button"
        className={`np-a-open${open ? ' is-open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-label="Notes"
        aria-expanded={open}
        title="Notes (n)"
      >
        <Pencil />
        {note.text.trim() && <span className="np-a-dot" />}
      </button>
      {open && (
        <section className="np-a-panel" aria-label="Notes">
          <header className="np-a-head">
            <span className="np-label">Notes</span>
            <kbd>n</kbd>
            <button type="button" className="np-a-close" onClick={() => setOpen(false)} aria-label="Close notes">
              ×
            </button>
          </header>
          <textarea
            autoFocus
            className="np-text"
            value={note.text}
            onChange={(e) => note.edit(e.target.value)}
            onBlur={note.flush}
            onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
            placeholder="Anything to come back to"
          />
          <p className={`np-status is-${note.status}`}>{STATUS[note.status]}</p>
        </section>
      )}
    </>
  )
}

/** B: a notes column pinned in the empty right margin. Folds to a slim edge tab. */
function VariantB({ note }: { note: SessionNote }) {
  const [open, setOpen] = useState(() => window.innerWidth >= 1280)

  if (!open) {
    return (
      <button type="button" className="np-b-tab" onClick={() => setOpen(true)} aria-label="Open notes">
        <Pencil />
        <span className="np-b-tab-label">Notes</span>
        {note.text.trim() && <span className="np-a-dot np-b-dot" />}
      </button>
    )
  }
  return (
    <aside className="np-b-column" aria-label="Notes">
      <header className="np-b-head">
        <span className="np-label">Notes</span>
        <button type="button" className="np-b-fold" onClick={() => setOpen(false)} aria-label="Fold notes">
          ›
        </button>
      </header>
      <textarea
        className="np-text"
        value={note.text}
        onChange={(e) => note.edit(e.target.value)}
        onBlur={note.flush}
        placeholder="Anything to come back to"
      />
      <p className={`np-status is-${note.status}`}>{STATUS[note.status]}</p>
    </aside>
  )
}

/** C: a one-line input docked under the content. Enter adds the line; the toggle opens the whole note. */
function VariantC({ note }: { note: SessionNote }) {
  const [line, setLine] = useState('')
  const [open, setOpen] = useState(false)
  const lines = note.text.split('\n').filter((l) => l.trim()).length

  const add = () => {
    const l = line.trim()
    if (!l) return
    const kept = note.text.replace(/\s+$/, '')
    note.edit(kept ? `${kept}\n${l}` : l)
    setLine('')
  }

  return (
    <div className="np-c">
      {open && (
        <section className="np-c-sheet" aria-label="Notes">
          <header className="np-b-head">
            <span className="np-label">Notes</span>
            <span className={`np-status is-${note.status}`}>{STATUS[note.status]}</span>
          </header>
          <textarea
            className="np-text"
            value={note.text}
            onChange={(e) => note.edit(e.target.value)}
            onBlur={note.flush}
            placeholder="Anything to come back to"
          />
        </section>
      )}
      <div className="np-c-bar">
        <Pencil />
        <input
          className="np-c-input"
          value={line}
          onChange={(e) => setLine(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault()
              add()
            }
          }}
          placeholder="Jot a note, Enter to add"
          aria-label="Jot a note"
        />
        <button type="button" className="np-c-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Notes <span className="np-c-count">{lines}</span> {open ? '▾' : '▴'}
        </button>
      </div>
    </div>
  )
}
