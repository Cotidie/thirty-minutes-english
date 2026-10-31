import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useChunks } from '../lib/useChunks'
import { useGenerationJob } from '../lib/useGenerationJob'
import type { TopicEntry, TopicLibrary } from '../types'
import { ConfirmDelete } from './ConfirmDelete'
import { GenerationProgress } from './GenerationProgress'
import { SessionLinks } from './SessionLinks'

type Used = 'all' | 'used' | 'unused'

/** Every topic, newest first: the curated pool, each day's news, and the ones typed in for a session. Any of them can
 * become a session from here; this page is the admin's, and the admin may always create one. */
export function TopicsPanel() {
  const navigate = useNavigate()
  const open = useCallback((sessionId: number) => navigate(`/s/${sessionId}`), [navigate])
  const { job, running: busy, error: jobError, start: generate, close } = useGenerationJob(open)
  const [library, setLibrary] = useState<TopicLibrary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [used, setUsed] = useState<Used>('all')

  useEffect(() => {
    api.topicLibrary().then(setLibrary).catch((e: Error) => setError(e.message))
  }, [])

  const found = useMemo(() => {
    const q = query.trim().toLowerCase()
    return [...(library?.topics ?? [])]
      .reverse()
      .filter(
        (t) =>
          (!q || t.text.toLowerCase().includes(q)) &&
          (category === 'all' || t.category === category) &&
          (used === 'all' || (used === 'used') === t.sessions.length > 0),
      )
  }, [library, query, category, used])
  const { shown, more, sentinel } = useChunks(found, [query, category, used].join('|'))

  async function remove(id: number) {
    await api.deleteTopic(id)
    setLibrary((l) => l && { ...l, topics: l.topics.filter((t) => t.id !== id) })
  }

  return (
    <>
      <p className="database-lede">Every topic: the curated pool, each day's news, and the ones you typed in.</p>
      <div className="db-filters">
        <input type="search" className="db-search" placeholder="Search the topics" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label htmlFor="topics-category">Category</label>
        <select id="topics-category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="all">All</option>
          {Object.entries(library?.labels ?? {}).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
        <label htmlFor="topics-used">Used</label>
        <select id="topics-used" value={used} onChange={(e) => setUsed(e.target.value as Used)}>
          <option value="all">All</option>
          <option value="used">In a session</option>
          <option value="unused">Not yet</option>
        </select>
      </div>

      {error && <p className="error">Could not load the topics: {error}</p>}
      {library && <p className="db-count">{`${found.length} of ${library.topics.length}`}</p>}
      <ol className="db-list">
        {shown.map((t) => (
          <TopicItem
            key={t.id}
            topic={t}
            label={library?.labels[t.category] ?? t.category}
            busy={busy}
            onCreate={() => void generate(t.text)}
            onDelete={() => remove(t.id)}
          />
        ))}
      </ol>
      {more && <div ref={sentinel} className="db-more" aria-hidden="true" />}
      {(job || jobError) && (
        <div className="db-job">
          {job && <GenerationProgress job={job} onClose={close} onOpen={open} />}
          {jobError && <p className="error">Could not create the session: {jobError}</p>}
        </div>
      )}
    </>
  )
}

interface TopicItemProps {
  topic: TopicEntry
  label: string
  /** A session is being written, and only one is at a time. */
  busy: boolean
  onCreate: () => void
  onDelete: () => Promise<void>
}

/** A topic a session was written on has no delete: the session needs it. */
function TopicItem({ topic, label, busy, onCreate, onDelete }: TopicItemProps) {
  const news = topic.news_days.length > 0 && `In the news on ${topic.news_days.map(formatDay).join(', ')}`
  return (
    <li className="db-item">
      <div className="db-head">
        <h2 className="topic-text">{topic.text}</h2>
        {topic.sessions.length === 0 && <ConfirmDelete label={topic.text} onDelete={onDelete} />}
        <button type="button" className="btn-link db-create" aria-label={`Create a session on ${topic.text}`} disabled={busy} onClick={onCreate}>
          Create session
        </button>
      </div>
      <p className="db-meta topic-meta">
        <span className="topic-category" data-category={topic.category}>
          {label}
        </span>
        {news}
        {news && topic.sessions.length > 0 && ' · '}
        {topic.sessions.length > 0 && (
          <>
            {'Used in '}
            <SessionLinks ids={topic.sessions} />
          </>
        )}
        {!news && topic.sessions.length === 0 && 'Not used yet'}
      </p>
    </li>
  )
}

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
