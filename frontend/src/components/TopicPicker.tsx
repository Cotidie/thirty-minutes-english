import { useState } from 'react'
import type { Category, Topic } from '../types'

interface Props {
  suggestions: Topic[]
  busy: boolean
  onGenerate: (topic: string | null) => void
}

/** Colour carries the category, so the key names what each colour means. */
const CATEGORY_LABELS: Record<Category, string> = {
  news: 'In the news',
  tech: 'Technology',
  literature: 'Literature',
  history: 'History',
  world: 'World',
}

const CATEGORY_ORDER: Category[] = ['news', 'tech', 'literature', 'history', 'world']

export function TopicPicker({ suggestions, busy, onGenerate }: Props) {
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
      <label htmlFor="topic" className="topic-label">
        Today's topic
      </label>
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
