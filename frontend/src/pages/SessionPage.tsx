import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, type ApiError } from '../api'
import { SharePanel } from '../components/SharePanel'
import { useAuth } from '../lib/auth'
import { useDrawingPictures } from '../lib/useDrawingPictures'
import { useSessionGone, useSessionResource } from '../lib/sessionChanges'
import { ArticleTab } from '../components/ArticleTab'
import { ExpressionsTab } from '../components/ExpressionsTab'
import { NoteBox } from '../components/NoteBox'
import { SessionTimer } from '../components/SessionTimer'
import { SummaryTab } from '../components/SummaryTab'
import { VocabularyTab } from '../components/VocabularyTab'
import { PHASES } from '../lib/phases'
import { useExamples } from '../lib/useExamples'
import { useNote } from '../lib/useNote'
import { useStars } from '../lib/useStars'
import type { Session, SessionContent } from '../types'
import './SessionPage.css'

/** Sits after the timed phases. */
const SUMMARY_TAB = PHASES.length
/** Each tab's name in the address (/s/19#vocabulary), so a reload stays on it. */
const TAB_KEYS = [...PHASES.map((p) => p.key), 'summary']

/** The session, or a plain notice once it cannot be opened: leaving `OpenSession` also closes its stream. */
export function SessionPage() {
  const { id } = useParams()
  const [goneId, setGoneId] = useState<string | null>(null)
  if (goneId !== null && goneId === id) {
    return (
      <main className="session">
        <p className="empty">This session is no longer available.</p>
        <Link to="/">Back to sessions</Link>
      </main>
    )
  }
  return <OpenSession key={id} id={Number(id)} onGone={() => setGoneId(id ?? null)} />
}

function OpenSession({ id, onGone }: { id: number; onGone: () => void }) {
  const { me } = useAuth()
  const { stars, toggle } = useStars(id)
  const { examples, add: addExample } = useExamples(id)
  const note = useNote(id)
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { hash, search } = useLocation()
  const navigate = useNavigate()
  const tab = Math.max(0, TAB_KEYS.indexOf(hash.slice(1)))

  useSessionResource(
    id,
    'session',
    () => api.getSession(id),
    setSession,
    (e) => ((e as ApiError).status === 404 ? onGone() : setError(e.message)),
  )
  useSessionGone(id, onGone)
  const arriving = useDrawingPictures(id)
  const setContent = (update: (content: SessionContent) => Partial<SessionContent>) =>
    setSession((s) => s && { ...s, content: { ...s.content, ...update(s.content) } })

  const showTab = (index: number) => {
    navigate({ search, hash: TAB_KEYS[index] }, { replace: true })
    window.scrollTo({ top: 0 })
  }

  if (error && !session) {
    return (
      <main className="session">
        <p className="error">Could not load this session: {error}</p>
        <Link to="/">Back to sessions</Link>
      </main>
    )
  }
  if (!session) return <main className="session"><p className="empty">Loading…</p></main>

  const { content } = session
  const mayCreate = Boolean(me && (me.is_admin || me.can_create))
  return (
    <main className="session">
      <aside className="rail">
        <Link to="/" className="rail-back">All sessions</Link>
        <p className="rail-topic">{content.topic}</p>
        <SessionTimer />
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
        {session.mine && <SharePanel sessionId={session.id} canAdd={mayCreate} />}
      </aside>
      <NoteBox note={note} />
      <div className="content">
        {tab === 0 && (
          <ExpressionsTab
            items={content.expressions}
            starred={stars.expressions}
            onToggleStar={(id) => toggle('expressions', id)}
            onSwap={async (id) => {
              const next = await api.swapExpression(session.id, id)
              setContent((c) => ({ expressions: c.expressions.map((e) => (e.id === id ? next : e)) }))
            }}
            onAdd={async () => {
              const added = await api.addExpression(session.id)
              setContent((c) => ({ expressions: [...c.expressions, added] }))
            }}
          />
        )}
        {tab === 1 && <ArticleTab article={content.article} sessionId={session.id} />}
        {tab === 2 && (
          <VocabularyTab
            items={content.vocabulary}
            sessionId={session.id}
            arriving={arriving}
            canRedraw={session.mine && mayCreate}
            onPicture={(index, item) => setContent((c) => ({ vocabulary: c.vocabulary.map((v, i) => (i === index ? item : v)) }))}
            starred={stars.words}
            onToggleStar={(id) => toggle('words', id)}
            examples={examples}
            onExample={addExample}
          />
        )}
        {tab === SUMMARY_TAB && <SummaryTab sessionId={session.id} content={content} stars={stars} />}
      </div>
    </main>
  )
}
