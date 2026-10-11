import { type ReactNode, useEffect, useState } from 'react'
import { api } from '../api'
import type { Correction, Example, Reading, SessionContent, Stars } from '../types'
import { SummaryCard } from './SummaryCard'
import './SummaryTab.css'

interface Props {
  sessionId: number
  content: SessionContent
  stars: Stars
  /** What the pair typed in the Notes box, as typed. */
  note: string
}

/**
 * What the session left behind: the pair's notes, what they starred, the
 * sentences they made, and the words the assessor stopped the reader on.
 */
export function SummaryTab({ sessionId, content, stars, note }: Props) {
  const [examples, setExamples] = useState<Example[] | null>(null)
  const [readings, setReadings] = useState<Reading[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    Promise.all([api.listExamples(sessionId), api.listReadings(sessionId)])
      .then(([e, r]) => {
        if (!live) return
        setExamples(e)
        setReadings(r)
      })
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [sessionId])

  const corrections = (readings ?? []).flatMap((r) => r.corrections ?? [])
  // Session order, so the list reads the way the tabs did.
  const starredExpressions = content.expressions.filter((e) => stars.expressions.includes(e.phrase))
  const starredWords = content.vocabulary.filter((v) => stars.words.includes(v.word))
  const starredCount = starredExpressions.length + starredWords.length
  const loading = readings === null && error === null

  return (
    <section className="tab-panel">
      {error && <p className="error">Could not read the session back: {error}</p>}
      {loading && <p className="empty">Reading it back…</p>}

      <Section title="Notes">
        {note.trim() ? (
          <p className="summary-note">{note}</p>
        ) : (
          <p className="empty">Nothing noted. Type in the Notes box under the tabs.</p>
        )}
      </Section>

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

      <Section title="Reading to fix" count={readings === null ? undefined : corrections.length}>
        {readings?.length === 0 && <p className="empty">No paragraph read aloud yet. The Article tab has the button.</p>}
        {readings !== null && readings.length > 0 && corrections.length === 0 && (
          <p className="empty">The coach let every word through. Clean read.</p>
        )}
        <ol className="summary-cards">
          {corrections.map((c, i) => (
            <CorrectionCard key={`${c.word}-${i}`} correction={c} />
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

function CorrectionCard({ correction }: { correction: Correction }) {
  return (
    <SummaryCard
      label={correction.heard}
      line={correction.word}
      note={
        <>
          {correction.fix}
          {correction.repeated_ok && <span className="summary-ok">got it on the retry</span>}
        </>
      }
    />
  )
}
