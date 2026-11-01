import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { SessionCreator } from '../components/SessionCreator'
import { useAccountResource } from '../lib/sessionChanges'
import type { SessionSummary } from '../types'
import './HomePage.css'

export function HomePage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)

  useAccountResource(
    'sessions',
    api.listSessions,
    (list) => {
      setSessions(list)
      setLoadError(null)
    },
    (e) => setLoadError(e.message),
  )

  /** My own session is deleted; a shared one only leaves my list. */
  async function remove(session: SessionSummary) {
    setRemoveError(null)
    try {
      await (session.mine ? api.deleteSession(session.id) : api.leaveSession(session.id))
      setSessions((s) => s.filter((x) => x.id !== session.id))
    } catch (e) {
      setRemoveError((e as Error).message)
    }
  }

  return (
    <main className="home">
      <header className="home-header">
        <h1 className="brand">Thirty minutes of English</h1>
        <p className="lede">
          A few expressions, one short article, and the words around it. Everything you two need to talk for half an hour.
        </p>
      </header>

      <SessionCreator />
      {loadError && <p className="error">Could not load past sessions: {loadError}</p>}
      {removeError && <p className="error">{removeError}</p>}

      <section className="history">
        <h2 className="history-title">Past sessions</h2>
        {sessions.length === 0 ? (
          <p className="empty">Nothing yet. Sessions you make, and ones shared with you, appear here.</p>
        ) : (
          <ul className="history-list">
            {sessions.map((s) => (
              <li key={s.id} className="history-item">
                <time dateTime={s.created_at}>{formatDate(s.created_at)}</time>
                <Link to={`/s/${s.id}`} className="history-link">
                  {s.title}
                  <span className="history-topic">{s.topic}</span>
                  {s.shared_by && <span className="history-topic">Shared by {s.shared_by}</span>}
                </Link>
                <button
                  type="button"
                  className="btn btn-link"
                  onClick={() => void remove(s)}
                  aria-label={s.mine ? `Delete ${s.title}` : `Remove ${s.title} from your list`}
                >
                  {s.mine ? 'Delete' : 'Remove'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
