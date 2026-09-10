import { useState } from 'react'

interface Props {
  suggestions: string[]
  busy: boolean
  onGenerate: (topic: string | null) => void
}

export function TopicPicker({ suggestions, busy, onGenerate }: Props) {
  const [topic, setTopic] = useState('')
  const shown = suggestions.slice(0, 6)

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
        <ul className="chips" aria-label="Suggested topics">
          {shown.map((s) => (
            <li key={s}>
              <button type="button" className="chip" disabled={busy} onClick={() => setTopic(s)}>
                {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
