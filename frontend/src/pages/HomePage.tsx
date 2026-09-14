import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { GenerationProgress } from '../components/GenerationProgress'
import { TopicPicker } from '../components/TopicPicker'
import type { JobStatus } from '../lib/progress'
import type { SessionSummary, Topic } from '../types'

/** How often to look back for the day's news topics while they are still coming. */
const TOPIC_POLL_MS = 15_000
const TOPIC_POLL_LIMIT = 12

export function HomePage() {
  const navigate = useNavigate()
  const [topics, setTopics] = useState<Topic[]>([])
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [job, setJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const busy = job !== null && job.status === 'running'

  useEffect(() => {
    api.listSessions().then(setSessions).catch((e: Error) => setError(e.message))
  }, [])

  // Today's news topics are fetched on the server the first time anyone asks.
  // Until they land, the pool fills the list, so keep looking for a while.
  useEffect(() => {
    let live = true
    let tries = 0
    const load = () => {
      api
        .topics()
        .then((listing) => {
          if (!live) return
          setTopics(listing.topics)
          if (listing.pending && ++tries < TOPIC_POLL_LIMIT) window.setTimeout(load, TOPIC_POLL_MS)
        })
        .catch(() => live && setTopics([]))
    }
    load()
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    if (!busy || !job) return
    const timer = setInterval(() => {
      api
        .getJob(job.id)
        .then((next) => {
          setJob(next)
          if (next.status === 'done' && next.session_id !== null) navigate(`/s/${next.session_id}`)
          if (next.status === 'failed') setError(next.error ?? 'generation failed')
        })
        .catch((e: Error) => {
          setError(e.message)
          setJob(null)
        })
    }, 1000)
    return () => clearInterval(timer)
  }, [busy, job, navigate])

  async function generate(topic: string | null) {
    setError(null)
    try {
      setJob(await api.startGeneration(topic))
    } catch (e) {
      setError((e as Error).message)
      setJob(null)
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
      {job && job.status !== 'failed' && <GenerationProgress job={job} />}
      {error && <p className="error">Could not create the session: {error}</p>}

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
