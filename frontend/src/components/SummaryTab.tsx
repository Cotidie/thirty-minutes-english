import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import type { Example, SessionContent, Stars, Summary } from '../types'
import { SummaryCard } from './SummaryCard'
import './SummaryTab.css'

interface Props {
  sessionId: number
  content: SessionContent
  stars: Stars
}

/**
 * What the session left behind: what the pair starred, the sentences they made, and the
 * paragraphs they summed up. The note has its own button; read-aloud marks stay on the article.
 */
export function SummaryTab({ sessionId, content, stars }: Props) {
  const [examples, setExamples] = useState<Example[] | null>(null)
  const [summaries, setSummaries] = useState<Summary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    Promise.all([api.listExamples(sessionId), api.listSummaries(sessionId)])
      .then(([e, s]) => {
        if (!live) return
        setExamples(e)
        setSummaries(s)
      })
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [sessionId])

  // Session order, so the list reads the way the tabs did.
  const starredExpressions = content.expressions.filter((e) => stars.expressions.includes(e.phrase))
  const starredWords = content.vocabulary.filter((v) => stars.words.includes(v.word))
  const starredCount = starredExpressions.length + starredWords.length
  const paragraphText = new Map(content.article.paragraphs.map((p) => [p.id, p.text]))
  const loading = examples === null && error === null

  return (
    <section className="tab-panel">
      {error && <p className="error">Could not read the session back: {error}</p>}
      {loading && <p className="empty">Reading it back…</p>}

      <Section title="Starred" count={starredCount}>
        {starredCount === 0 && <p className="empty">Nothing starred. Tap ☆ on an expression or word card.</p>}
        {starredCount > 0 && (
          <ul className="starred-list">
            {starredExpressions.map((e) => (
              <li key={`e-${e.phrase}`}>
                <span className="starred-term">{e.phrase}</span>
                <span className="starred-gloss">{e.meaning}</span>
              </li>
            ))}
            {starredWords.map((v) => (
              <li key={`w-${v.word}`}>
                <span className="starred-term">
                  {v.word} <em className="vocab-pos">{v.pos}</em>
                </span>
                <span className="starred-gloss">{v.definition}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Sentences you made" count={examples?.length}>
        {examples?.length === 0 && <p className="empty">No sentences yet. Each expression has a Your turn button.</p>}
        <ol className="summary-cards">
          {examples?.map((ex) => (
            <SummaryCard key={ex.id} label={ex.expression} line={ex.user_text} note={ex.coach_text} />
          ))}
        </ol>
      </Section>

      <Section title="Paragraphs you summed up" count={summaries?.length}>
        {summaries?.length === 0 && <p className="empty">No summaries yet. Each paragraph in the Article tab has a Summarize button.</p>}
        <ol className="summary-cards">
          {summaries?.map((s) => (
            <SummaryCard key={s.id} label={`${(paragraphText.get(s.paragraph_id) ?? '').split(/\s+/).slice(0, 4).join(' ')}…`} line={s.user_text} note={s.feedback.summary} />
          ))}
        </ol>
      </Section>
    </section>
  )
}

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="summary-section">
      <h2 className="summary-title">
        {title}
        {count !== undefined && <span className="summary-count">{count}</span>}
      </h2>
      {children}
    </section>
  )
}
