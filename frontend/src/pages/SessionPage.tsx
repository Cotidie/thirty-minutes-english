import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { ArticleTab } from '../components/ArticleTab'
import { ExpressionsTab } from '../components/ExpressionsTab'
import { SessionTimer } from '../components/SessionTimer'
import { VocabularyTab } from '../components/VocabularyTab'
import { PHASES } from '../lib/phases'
import type { Session } from '../types'

export function SessionPage() {
  const { id } = useParams()
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState(0)

  useEffect(() => {
    api.getSession(Number(id)).then(setSession).catch((e: Error) => setError(e.message))
  }, [id])

  const showTab = useCallback((index: number) => {
    setTab(index)
    window.scrollTo({ top: 0 })
  }, [])

  if (error) {
    return (
      <main className="session">
        <p className="error">Could not load this session: {error}</p>
        <Link to="/">Back to sessions</Link>
      </main>
    )
  }
  if (!session) return <main className="session"><p className="empty">Loading…</p></main>

  const { content } = session
  return (
    <main className="session">
      <aside className="rail">
        <Link to="/" className="rail-back">All sessions</Link>
        <p className="rail-topic">{content.topic}</p>
        <SessionTimer onPhaseChange={showTab} />
        <nav className="tabs" aria-label="Session parts">
          {PHASES.map((p, i) => (
            <button
              key={p.key}
              type="button"
              className={`tab${i === tab ? ' is-active' : ''}`}
              aria-current={i === tab ? 'page' : undefined}
              onClick={() => showTab(i)}
            >
              <span className="tab-index">{i + 1}</span>
              <span className="tab-label">{p.label}</span>
              <span className="tab-minutes">{p.minutes} min</span>
            </button>
          ))}
        </nav>
        <nav className="rail-links" aria-label="Saved work">
          <Link to={`/asks?session_id=${session.id}`} className="rail-link">
            Asks
          </Link>
        </nav>
      </aside>
      <div className="content">
        {tab === 0 && <ExpressionsTab items={content.expressions} />}
        {tab === 1 && <ArticleTab article={content.article} />}
        {tab === 2 && <VocabularyTab items={content.vocabulary} />}
      </div>
    </main>
  )
}
