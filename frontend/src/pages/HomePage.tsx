import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { TopicPicker } from '../components/TopicPicker'
import type { SessionSummary } from '../types'

function shuffle<T>(items: T[]): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

export function HomePage() {
  const navigate = useNavigate()
  const [topics, setTopics] = useState<string[]>([])
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.topics().then((t) => setTopics(shuffle(t))).catch(() => setTopics([]))
    api.listSessions().then(setSessions).catch((e: Error) => setError(e.message))
  }, [])

  async function generate(topic: string | null) {
    setBusy(true)
    setError(null)
    try {
      const session = await api.createSession(topic)
      navigate(`/s/${session.id}`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  async function remove(id: number) {
    await api.deleteSession(id)
    setSessions((s) => s.filter((x) => x.id !== id))
  }

  return (
    <main className="home">
      <header className="home-header">
        <h1 className="brand">Thirty minutes of English</h1>
        <p className="lede">
          Six expressions, one short article, twelve words. Everything you two need to talk for half an hour.
        </p>
      </header>

      <TopicPicker suggestions={topics} busy={busy} onGenerate={generate} />
      {error && <p className="error">Could not create the session: {error}</p>}

      <section className="history">
        <h2 className="history-title">Past sessions</h2>
        {sessions.length === 0 ? (
          <p className="empty">Nothing yet. Generate the first session above.</p>
        ) : (
          <ul className="history-list">
            {sessions.map((s) => (
              <li key={s.id} className="history-item">
                <time dateTime={s.created_at}>{formatDate(s.created_at)}</time>
                <Link to={`/s/${s.id}`} className="history-link">
                  {s.title}
                  <span className="history-topic">{s.topic}</span>
                </Link>
                <button type="button" className="btn btn-link" onClick={() => remove(s.id)} aria-label={`Delete ${s.title}`}>
                  Delete
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
