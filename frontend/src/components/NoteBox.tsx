import type { NoteStatus, SessionNote } from '../lib/useNote'
import './NoteBox.css'

const STATUS: Record<NoteStatus, string> = {
  saved: 'Saved',
  saving: 'Saving…',
  failed: 'Not saved. Type to retry.',
}

/** The session's notepad in the rail, open on every tab. */
export function NoteBox({ note }: { note: SessionNote }) {
  return (
    <section className="note">
      <label className="note-label" htmlFor="session-note">
        Notes
      </label>
      <textarea
        id="session-note"
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
  )
}
