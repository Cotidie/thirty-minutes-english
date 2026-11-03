import { useCallback, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '../lib/auth'
import { type Leaving, useCloseOnLeave } from '../lib/useCloseOnLeave'
import { USERNAME_HINT, cleanUsername, isUsername } from '../lib/username'
import './NameTag.css'

/** My username among the corner tools: what others find me by and see on my cursor. Pressing it opens a box to change it. */
export function NameTag() {
  const { me, rename } = useAuth()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [tried, setTried] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const here = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  /** Focus goes back to the button unless a press elsewhere already took it. */
  const close = useCallback((how: Leaving | 'saved') => {
    setOpen(false)
    if (how !== 'outside') button.current?.focus()
  }, [])
  useCloseOnLeave(open, here, close)

  if (!me) return null
  const bad = tried && !isUsername(draft)

  function toggle() {
    if (!open && me) {
      setDraft(me.username)
      setTried(false)
      setError(null)
    }
    setOpen((was) => !was)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setTried(true)
    setError(null)
    if (!isUsername(draft)) return
    setBusy(true)
    try {
      await rename(cleanUsername(draft))
      close('saved')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="name-tag" ref={here}>
      <button
        ref={button}
        type="button"
        className="corner-button name-tag-button"
        aria-label={`Username ${me.username}`}
        aria-expanded={open}
        title="Your username"
        onClick={toggle}
      >
        {me.username}
      </button>
      {open && (
        <div className="name-tag-panel" role="dialog" aria-label="Username">
          <form noValidate onSubmit={(e) => void save(e)}>
            <label htmlFor="name-tag-input" className="name-tag-label">
              Others know you as
            </label>
            <input
              id="name-tag-input"
              className={`name-tag-input${bad ? ' is-bad' : ''}`}
              autoComplete="nickname"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <p className={`name-tag-hint${bad ? ' is-bad' : ''}`}>{USERNAME_HINT}</p>
            {error && (
              <p role="alert" className="name-tag-error">
                {error}
              </p>
            )}
            <button type="submit" className="btn btn-primary name-tag-save" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
