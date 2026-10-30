import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { SessionCreator } from '../components/SessionCreator'
import { useAuth } from '../lib/auth'
import { useAccountResource } from '../lib/sessionChanges'
import type { SessionSummary } from '../types'
import './HomePage.css'

export function HomePage() {
  const { me } = useAuth()
  const canCreate = Boolean(me && (me.is_admin || me.can_create))
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

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
    await (session.mine ? api.deleteSession(session.id) : api.leaveSession(session.id))
    setSessions((s) => s.filter((x) => x.id !== session.id))
  }

  return (
    <main className="home">
      <header className="home-header">
        <h1 className="brand">Thirty minutes of English</h1>
        <p className="lede">
          A few expressions, one short article, and the words around it. Everything you two need to talk for half an hour.
        </p>
      </header>

      {canCreate ? (
        <SessionCreator />
      ) : (
        <p className="home-locked">Session creation isn't on for this account yet. Ask the admin to turn it on.</p>
      )}
      {loadError && <p className="error">Could not load past sessions: {loadError}</p>}

      <section className="history">
        <h2 className="history-title">Past sessions</h2>
        {sessions.length === 0 ? (
          <p className="empty">{canCreate ? 'Nothing yet. Generate the first session above.' : 'Nothing here yet. Sessions shared with you appear here.'}</p>
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
