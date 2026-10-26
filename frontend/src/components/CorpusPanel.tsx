import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { CorpusEntry } from '../types'
import { SessionLinks } from './SessionLinks'

type Source = 'youtube' | 'instagram'
type Taught = 'all' | 'new' | 'taught'

const SOURCE_LABEL: Record<Source, string> = { youtube: 'YouTube post', instagram: 'Instagram post' }

function sourceOf(entry: CorpusEntry): Source {
  return entry.source.includes('instagram.com') ? 'instagram' : 'youtube'
}

/** The expression corpus new sessions pick from, to read through: search and filters, nothing to edit. */
export function CorpusPanel() {
  const [corpus, setCorpus] = useState<CorpusEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [setting, setSetting] = useState('all')
  const [source, setSource] = useState<Source | 'all'>('all')
  const [taught, setTaught] = useState<Taught>('all')

  useEffect(() => {
    api.corpus().then(setCorpus).catch((e: Error) => setError(e.message))
  }, [])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (corpus ?? []).filter(
      (e) =>
        (!q || [e.phrase, e.meaning, e.korean ?? ''].some((text) => text.toLowerCase().includes(q))) &&
        (setting === 'all' || e.setting === setting) &&
        (source === 'all' || sourceOf(e) === source) &&
        (taught === 'all' || (taught === 'taught') === e.sessions.length > 0),
    )
  }, [corpus, query, setting, source, taught])

  return (
    <>
      <p className="database-lede">Every expression a new session can pick its five from.</p>
      <div className="db-filters">
        <input
          type="search"
          className="db-search"
          placeholder="Search the phrase, meaning or Korean"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label htmlFor="corpus-setting">Setting</label>
        <select id="corpus-setting" value={setting} onChange={(e) => setSetting(e.target.value)}>
          <option value="all">All</option>
          <option value="casual">Casual</option>
          <option value="workplace">Workplace</option>
          <option value="discussion">Discussion</option>
        </select>
        <label htmlFor="corpus-source">Source</label>
        <select id="corpus-source" value={source} onChange={(e) => setSource(e.target.value as Source | 'all')}>
          <option value="all">All</option>
          <option value="youtube">YouTube</option>
          <option value="instagram">Instagram</option>
        </select>
        <label htmlFor="corpus-taught">Taught</label>
        <select id="corpus-taught" value={taught} onChange={(e) => setTaught(e.target.value as Taught)}>
          <option value="all">All</option>
          <option value="new">Not yet</option>
          <option value="taught">Taught</option>
        </select>
      </div>

      {error && <p className="error">Could not load the corpus: {error}</p>}
      {corpus && <p className="db-count">{`${shown.length} of ${corpus.length}`}</p>}
      <ol className="db-list">
        {shown.map((entry) => (
          <CorpusItem key={entry.id} entry={entry} />
        ))}
      </ol>
    </>
  )
}

function CorpusItem({ entry }: { entry: CorpusEntry }) {
  return (
    <li className="db-item">
      <div className="db-head">
        <h2 className="corpus-phrase">{entry.phrase}</h2>
        {entry.setting && <span className="corpus-setting">{entry.setting}</span>}
      </div>
      {entry.korean && <p className="corpus-korean">{entry.korean}</p>}
      <p className="corpus-meaning">
        {entry.meaning}
        {entry.synonyms && entry.synonyms.length > 0 && <span className="corpus-synonyms"> ≈ {entry.synonyms.join(', ')}</span>}
      </p>
      <p className="corpus-note">{entry.usage_note}</p>
      {entry.examples.length > 0 && (
        <ul className="corpus-examples">
          {entry.examples.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      )}
      <p className="db-meta">
        <a href={entry.source} target="_blank" rel="noreferrer">
          {SOURCE_LABEL[sourceOf(entry)]}
        </a>
        {entry.sessions.length > 0 && (
          <>
            {' · Taught in '}
            <SessionLinks ids={entry.sessions} />
          </>
        )}
      </p>
    </li>
  )
}
