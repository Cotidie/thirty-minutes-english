import { type ReactNode, useState } from 'react'
import { api } from '../api'
import { useSessionResource } from '../lib/sessionChanges'
import { speakerOf } from '../lib/speaker'
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

  useSessionResource(
    sessionId,
    'records',
    () => Promise.all([api.listExamples(sessionId), api.listSummaries(sessionId)]),
    ([e, s]) => {
      setExamples(e)
      setSummaries(s)
      setError(null)
    },
    (e) => setError(e.message),
  )

  // Session order, so the list reads the way the tabs did.
  const starredExpressions = content.expressions.filter((e) => stars.expressions.includes(e.id))
  const starredWords = content.vocabulary.filter((v) => stars.words.includes(v.id))
  const word = new Map(content.vocabulary.map((v) => [v.id, v.word]))
  const madeWith = (ex: Example) => word.get(ex.vocabulary_id) ?? ''
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
        {examples?.length === 0 && <p className="empty">No sentences yet. Each word has a Practice button.</p>}
        <ol className="summary-cards">
          {examples?.map((ex) => (
            <SummaryCard key={ex.id} label={madeWith(ex)} line={ex.user_text} note={ex.coach_text} />
          ))}
        </ol>
      </Section>

      <Section title="Paragraphs summed up" count={summaries?.length}>
        {summaries?.length === 0 && <p className="empty">No summaries yet. Each paragraph in the Article tab has a Summarize button.</p>}
        <ol className="summary-cards">
          {summaries?.map((s) => (
            <SummaryCard key={s.id} label={`${speakerOf(s)} · ${opening(paragraphText.get(s.paragraph_id) ?? '')}`} line={s.user_text} note={feedbackNote(s)} />
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

/** The first four words of a paragraph, to tell which one a summary is of. */
function opening(text: string): string {
  return `${text.split(/\s+/).slice(0, 4).join(' ')}…`
}

/** The model answer once the feedback is in; otherwise where it is. */
function feedbackNote(summary: Summary): string {
  if (summary.status === 'judging') return 'Waiting for feedback…'
  if (summary.status === 'failed' || !summary.feedback) return 'No feedback: judge it again in the Article tab.'
  return summary.feedback.summary
}
