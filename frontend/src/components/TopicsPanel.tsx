import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useChunks } from '../lib/useChunks'
import type { TopicEntry, TopicLibrary } from '../types'
import { ConfirmDelete } from './ConfirmDelete'
import { SessionLinks } from './SessionLinks'

type Used = 'all' | 'used' | 'unused'

/** Every topic, newest first: the curated pool, each day's news, and the ones typed in for a session. */
export function TopicsPanel() {
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
          <TopicItem key={t.id} topic={t} label={library?.labels[t.category] ?? t.category} onDelete={() => remove(t.id)} />
        ))}
      </ol>
      {more && <div ref={sentinel} className="db-more" aria-hidden="true" />}
    </>
  )
}

/** A topic a session was written on has no delete: the session needs it. */
function TopicItem({ topic, label, onDelete }: { topic: TopicEntry; label: string; onDelete: () => Promise<void> }) {
  const news = topic.news_days.length > 0 && `In the news on ${topic.news_days.map(formatDay).join(', ')}`
  return (
    <li className="db-item">
      <div className="db-head">
        <h2 className="topic-text">{topic.text}</h2>
        <span className="topic-category" data-category={topic.category}>
          {label}
        </span>
        {topic.sessions.length === 0 && <ConfirmDelete label={topic.text} onDelete={onDelete} />}
      </div>
      <p className="db-meta">
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
