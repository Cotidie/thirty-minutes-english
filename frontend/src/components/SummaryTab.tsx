import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Ask, Correction, Example, Reading, SessionContent, Stars } from '../types'

interface Props {
  sessionId: number
  content: SessionContent
  stars: Stars
}

/**
 * What the session left behind: what the pair starred, the sentences they
 * made, the expressions the coach handed over, and the words it stopped the
 * reader on. The last two are extracted from transcripts the first time this
 * tab is opened, then kept.
 */
export function SummaryTab({ sessionId, content, stars }: Props) {
  const [asks, setAsks] = useState<Ask[] | null>(null)
  const [examples, setExamples] = useState<Example[] | null>(null)
  const [readings, setReadings] = useState<Reading[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    Promise.all([api.askCards(sessionId), api.listExamples(sessionId), api.readingCorrections(sessionId)])
      .then(([a, e, r]) => {
        if (!live) return
        setAsks(a)
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
  const loading = asks === null && readings === null && error === null

  return (
    <section className="tab-panel">
      {error && <p className="error">Could not read the session back: {error}</p>}
      {loading && <p className="empty">Reading it back…</p>}

      <section className="summary-section">
        <h2 className="summary-title">
          Starred
          <span className="summary-count">{starredCount}</span>
        </h2>
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
      </section>

      <section className="summary-section">
        <h2 className="summary-title">
          Sentences you made
          {examples !== null && <span className="summary-count">{examples.length}</span>}
        </h2>
        {examples?.length === 0 && <p className="empty">No sentences yet. Each expression has a Your turn button.</p>}
        <ol className="ask-cards">
          {examples?.map((ex) => (
            <li key={ex.id} className="ask-card">
              <p className="ask-card-asked">{ex.expression}</p>
              <div className="ask-card-body">
                <p className="ask-card-english">{ex.user_text}</p>
                <p className="ask-card-note">{ex.coach_text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="summary-section">
        <h2 className="summary-title">
          Expressions you asked for
          {asks !== null && <span className="summary-count">{asks.length}</span>}
        </h2>
        {asks?.length === 0 && <p className="empty">Nothing asked yet. Press A to ask the coach for one.</p>}
        <ol className="ask-cards">
          {asks?.map((ask) => (
            <li key={ask.id} className="ask-card">
              <p className="ask-card-asked">{ask.card?.asked || ask.user_text}</p>
              <div className="ask-card-body">
                {ask.card?.english ? (
                  <p className="ask-card-english">{ask.card.english}</p>
                ) : (
                  <p className="ask-card-english is-missing">No answer landed in this round.</p>
                )}
                {ask.card?.alternatives.map((alt) => (
                  <p key={alt} className="ask-card-alt">
                    {alt}
                  </p>
                ))}
                {ask.card?.note && <p className="ask-card-note">{ask.card.note}</p>}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="summary-section">
        <h2 className="summary-title">
          Reading to fix
          {readings !== null && <span className="summary-count">{corrections.length}</span>}
        </h2>
        {readings?.length === 0 && <p className="empty">No paragraph read aloud yet. The Article tab has the button.</p>}
        {readings !== null && readings.length > 0 && corrections.length === 0 && (
          <p className="empty">The coach let every word through. Clean read.</p>
        )}
        <ol className="ask-cards">
          {corrections.map((c, i) => (
            <CorrectionRow key={`${c.word}-${i}`} correction={c} />
          ))}
        </ol>
      </section>
    </section>
  )
}

function CorrectionRow({ correction }: { correction: Correction }) {
  return (
    <li className="ask-card">
      <p className="ask-card-asked">
        {correction.kind === 'phrasing' && <span className="correction-kind">phrasing</span>}
        {correction.heard}
      </p>
      <div className="ask-card-body">
        <p className="ask-card-english">{correction.word}</p>
        <p className="ask-card-note">
          {correction.fix}
          {correction.repeated_ok && <span className="summary-ok">got it on the retry</span>}
        </p>
      </div>
    </li>
  )
}
