import { useState } from 'react'
import type { Category, Topic } from '../types'

interface Props {
  suggestions: Topic[]
  /** The news half is still on its way; the list may change under you. */
  pending: boolean
  /** Why the news half is missing, when the last fetch failed. */
  error?: string | null
  busy: boolean
  onGenerate: (topic: string | null) => void
  onRefresh: () => void
}

/** Colour carries the category, so the key names what each colour means. */
const CATEGORY_LABELS: Record<Category, string> = {
  news: 'In the news',
  tech: 'Technology',
  literature: 'Literature',
  history: 'History',
  world: 'World',
  korea: 'Korea',
  research: 'Research',
}

const CATEGORY_ORDER: Category[] = ['news', 'korea', 'research', 'tech', 'literature', 'history', 'world']

export function TopicPicker({ suggestions, pending, error, busy, onGenerate, onRefresh }: Props) {
  const [topic, setTopic] = useState('')
  // The server decides how many the day offers, and in what order.
  const shown = suggestions
  const legend = CATEGORY_ORDER.filter((c) => shown.some((s) => s.category === c))

  return (
    <form
      className="topic-picker"
      onSubmit={(e) => {
        e.preventDefault()
        onGenerate(topic.trim() || null)
      }}
    >
      <div className="topic-head">
        <label htmlFor="topic" className="topic-label">
          Today's topic
        </label>
        <button
          type="button"
          className={`topic-refresh${pending ? ' is-pending' : ''}`}
          aria-label="Refresh suggestions"
          title={pending ? 'Looking for today\'s news…' : 'Deal new suggestions'}
          disabled={pending || busy}
          onClick={onRefresh}
        >
          ↻
        </button>
      </div>
      {error && !pending && (
        <p className="topic-notice" role="status">
          Today's news could not be fetched: {error}. These are all from the standing pool.
        </p>
      )}
      <div className="topic-row">
        <input
          id="topic"
          className="topic-input"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Leave empty to let Claude choose"
          disabled={busy}
          autoComplete="off"
        />
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Writing…' : 'Generate session'}
        </button>
      </div>
      {shown.length > 0 && (
        <>
          <ul className="chips" aria-label="Suggested topics">
            {shown.map((s) => (
              <li key={s.text}>
                <button
                  type="button"
                  className="chip"
                  data-category={s.category}
                  disabled={busy}
                  onClick={() => setTopic(s.text)}
                >
                  {s.text}
                </button>
              </li>
            ))}
          </ul>
          <ul className="chip-key" aria-label="Topic categories">
            {legend.map((c) => (
              <li key={c} data-category={c}>
                {CATEGORY_LABELS[c]}
              </li>
            ))}
          </ul>
        </>
      )}
    </form>
  )
}
