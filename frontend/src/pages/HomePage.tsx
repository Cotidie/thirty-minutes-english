import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { GenerationProgress } from '../components/GenerationProgress'
import { TopicPicker } from '../components/TopicPicker'
import { useGenerationJob } from '../lib/useGenerationJob'
import { useTopics } from '../lib/useTopics'
import type { SessionSummary } from '../types'
import './HomePage.css'

export function HomePage() {
  const navigate = useNavigate()
  const { topics, labels: topicLabels, pending, error: topicError, refresh } = useTopics()
  const open = useCallback((sessionId: number) => navigate(`/s/${sessionId}`), [navigate])
  const { job, running: busy, error, start: generate, cancel } = useGenerationJob(open)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    api.listSessions().then(setSessions).catch((e: Error) => setLoadError(e.message))
  }, [])

  async function remove(id: number) {
    await api.deleteSession(id)
    setSessions((s) => s.filter((x) => x.id !== id))
  }

  return (
    <main className="home">
      <header className="home-header">
        <h1 className="brand">Thirty minutes of English</h1>
        <p className="lede">
          A few expressions, one short article, and the words around it. Everything you two need to talk for half an hour.
        </p>
      </header>

      <TopicPicker
        suggestions={topics}
        labels={topicLabels}
        pending={pending}
        error={topicError}
        busy={busy}
        onGenerate={generate}
        onRefresh={refresh}
      />
      {job && job.status !== 'failed' && <GenerationProgress job={job} onCancel={cancel} />}
      {error && <p className="error">Could not create the session: {error}</p>}
      {loadError && <p className="error">Could not load past sessions: {loadError}</p>}

      <section className="history">
        <h2 className="history-title">
          Past sessions
          <Link to="/asks" className="history-aside">
            Asks
          </Link>
        </h2>
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
