import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { ArticleTab } from '../components/ArticleTab'
import { ExpressionsTab } from '../components/ExpressionsTab'
import { SessionTimer } from '../components/SessionTimer'
import { SummaryTab } from '../components/SummaryTab'
import { VocabularyTab } from '../components/VocabularyTab'
import { PHASES } from '../lib/phases'
import { useExamples } from '../lib/useExamples'
import { useStars } from '../lib/useStars'
import type { Session } from '../types'
import './SessionPage.css'

/** Sits after the timed phases; the timer never sends you here. */
const SUMMARY_TAB = PHASES.length
/** Each tab's name in the address (/s/19#vocabulary), so a reload stays on it. */
const TAB_KEYS = [...PHASES.map((p) => p.key), 'summary']

export function SessionPage() {
  const { id } = useParams()
  const { stars, toggle } = useStars(Number(id))
  const { examples, add: addExample } = useExamples(Number(id))
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { hash } = useLocation()
  const navigate = useNavigate()
  const tab = Math.max(0, TAB_KEYS.indexOf(hash.slice(1)))

  useEffect(() => {
    api.getSession(Number(id)).then(setSession).catch((e: Error) => setError(e.message))
  }, [id])

  const showTab = useCallback(
    (index: number) => {
      navigate({ hash: TAB_KEYS[index] }, { replace: true })
      window.scrollTo({ top: 0 })
    },
    [navigate],
  )

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
          <button
            type="button"
            className={`tab is-summary${tab === SUMMARY_TAB ? ' is-active' : ''}`}
            aria-current={tab === SUMMARY_TAB ? 'page' : undefined}
            onClick={() => showTab(SUMMARY_TAB)}
          >
            <span className="tab-index">{SUMMARY_TAB + 1}</span>
            <span className="tab-label">Summary</span>
            <span className="tab-minutes">after</span>
          </button>
        </nav>
      </aside>
      <div className="content">
        {tab === 0 && (
          <ExpressionsTab
            items={content.expressions}
            sessionId={session.id}
            starred={stars.expressions}
            onToggleStar={(phrase) => toggle('expressions', phrase)}
            examples={examples}
            onExample={addExample}
          />
        )}
        {tab === 1 && <ArticleTab article={content.article} sessionId={session.id} />}
        {tab === 2 && (
          <VocabularyTab
            items={content.vocabulary}
            sessionId={session.id}
            onPicture={(index, item) =>
              setSession((s) =>
                s && { ...s, content: { ...s.content, vocabulary: s.content.vocabulary.map((v, i) => (i === index ? item : v)) } },
              )
            }
            starred={stars.words}
            onToggleStar={(word) => toggle('words', word)}
            examples={examples}
            onExample={addExample}
          />
        )}
        {tab === SUMMARY_TAB && <SummaryTab sessionId={session.id} content={content} stars={stars} />}
      </div>
    </main>
  )
}
