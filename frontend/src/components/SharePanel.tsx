import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { useSessionResource } from '../lib/sessionChanges'
import type { ShareEntry } from '../types'
import './SharePanel.css'

interface Props {
  sessionId: number
  /** Whether this account may add people; anyone who made the session may end a share. */
  canAdd: boolean
}

/** Whom the maker of a session has shared it with. */
export function SharePanel({ sessionId, canAdd }: Props) {
  const [shares, setShares] = useState<ShareEntry[]>([])
  const [email, setEmail] = useState('')
  const [readError, setReadError] = useState<string | null>(null)
  const [writeError, setWriteError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const error = writeError ?? readError

  useSessionResource(
    sessionId,
    'shares',
    () => api.listShares(sessionId),
    (list) => {
      setShares(list)
      setReadError(null)
    },
    (e) => setReadError(e.message),
  )

  async function add(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setWriteError(null)
    try {
      setShares(await api.addShare(sessionId, email))
      setEmail('')
    } catch (e) {
      setWriteError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(entry: ShareEntry) {
    setWriteError(null)
    try {
      await api.removeShare(sessionId, entry.user_id)
      setShares((all) => all.filter((s) => s.user_id !== entry.user_id))
    } catch (e) {
      setWriteError((e as Error).message)
    }
  }

  if (!canAdd && shares.length === 0) return null

  return (
    <section className="share" aria-label="Sharing">
      {canAdd && (
        <form className="share-form" onSubmit={(e) => void add(e)}>
          <label htmlFor="share-email" className="share-label">
            Share with
          </label>
          <div className="share-row">
            <input
              id="share-email"
              type="email"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="their email"
              className="share-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button type="submit" className="btn" disabled={busy || !email.trim()}>
              Share
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="share-error">
          {error}
        </p>
      )}
      {shares.length > 0 && (
        <ul className="share-list">
          {shares.map((entry) => (
            <li key={entry.user_id} className="share-item">
              <span className="share-email" title={entry.email}>
                {entry.email}
              </span>
              <button
                type="button"
                className="btn-link share-stop"
                aria-label={`Stop sharing with ${entry.email}`}
                onClick={() => void remove(entry)}
              >
                Stop
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
