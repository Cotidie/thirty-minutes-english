import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useChunks } from '../lib/useChunks'
import type { CorpusEntry } from '../types'
import { ConfirmDelete } from './ConfirmDelete'
import { SessionLinks } from './SessionLinks'

type Source = 'youtube' | 'instagram'
type Used = 'all' | 'new' | 'used'

const SOURCE_LABEL: Record<Source, string> = { youtube: 'YouTube post', instagram: 'Instagram post' }

function sourceOf(entry: CorpusEntry): Source {
  return entry.source.includes('instagram.com') ? 'instagram' : 'youtube'
}

/** Taught in a session, or swapped out of one. */
function isUsed(entry: CorpusEntry): boolean {
  return entry.sessions.length + entry.swapped.length > 0
}

/** The expression corpus new sessions pick from, to read through with search and filters, and to prune. */
export function CorpusPanel() {
  const [corpus, setCorpus] = useState<CorpusEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [setting, setSetting] = useState('all')
  const [source, setSource] = useState<Source | 'all'>('all')
  const [used, setUsed] = useState<Used>('all')

  useEffect(() => {
    api.corpus().then(setCorpus).catch((e: Error) => setError(e.message))
  }, [])

  const found = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (corpus ?? []).filter(
      (e) =>
        (!q || [e.phrase, e.meaning, e.korean ?? ''].some((text) => text.toLowerCase().includes(q))) &&
        (setting === 'all' || e.setting === setting) &&
        (source === 'all' || sourceOf(e) === source) &&
        (used === 'all' || (used === 'used') === isUsed(e)),
    )
  }, [corpus, query, setting, source, used])
  const { shown, more, sentinel } = useChunks(found, [query, setting, source, used].join('|'))

  async function remove(id: number) {
    await api.deleteExpression(id)
    setCorpus((c) => c && c.filter((e) => e.id !== id))
  }

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
        <label htmlFor="corpus-used">Used</label>
        <select id="corpus-used" value={used} onChange={(e) => setUsed(e.target.value as Used)}>
          <option value="all">All</option>
          <option value="new">Not yet</option>
          <option value="used">In a session</option>
        </select>
      </div>

      {error && <p className="error">Could not load the corpus: {error}</p>}
      {corpus && <p className="db-count">{`${found.length} of ${corpus.length}`}</p>}
      <ol className="db-list">
        {shown.map((entry) => (
          <CorpusItem key={entry.id} entry={entry} onDelete={() => remove(entry.id)} />
        ))}
      </ol>
      {more && <div ref={sentinel} className="db-more" aria-hidden="true" />}
    </>
  )
}

function CorpusItem({ entry, onDelete }: { entry: CorpusEntry; onDelete: () => Promise<void> }) {
  const taughtIn = entry.sessions.map((id) => `Session ${id}`).join(', ')
  return (
    <li className="db-item">
      <div className="db-head">
        <h2 className="corpus-phrase">{entry.phrase}</h2>
        {entry.setting && <span className="corpus-setting">{entry.setting}</span>}
        <ConfirmDelete label={entry.phrase} warning={taughtIn && `Also takes it out of ${taughtIn}.`} onDelete={onDelete} />
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
        {entry.swapped.length > 0 && (
          <>
            {' · Swapped out of '}
            <SessionLinks ids={entry.swapped} />
          </>
        )}
      </p>
    </li>
  )
}
