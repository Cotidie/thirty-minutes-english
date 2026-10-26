import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { TopicEntry, TopicLibrary } from '../types'
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

  const shown = useMemo(() => {
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
      {library && <p className="db-count">{`${shown.length} of ${library.topics.length}`}</p>}
      <ol className="db-list">
        {shown.map((t) => (
          <TopicItem key={t.id} topic={t} label={library?.labels[t.category] ?? t.category} />
        ))}
      </ol>
    </>
  )
}

function TopicItem({ topic, label }: { topic: TopicEntry; label: string }) {
  const news = topic.news_days.length > 0 && `In the news on ${topic.news_days.map(formatDay).join(', ')}`
  return (
    <li className="db-item">
      <div className="db-head">
        <h2 className="topic-text">{topic.text}</h2>
        <span className="topic-category" data-category={topic.category}>
          {label}
        </span>
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
