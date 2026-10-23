import { useMemo } from 'react'
import type { Span } from '../lib/highlight'
import type { Piece } from '../lib/sentences'
import type { Summary } from '../types'
import { wordStarts, type Marks } from '../lib/words'
import { ReadAloudButton, ReadAloudPanel, useReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'
import { SummarizeButton, SummaryPanel, useSummary } from './Summarize'
import './Paragraph.css'

interface Props {
  paragraph: string
  /** The paragraph cut into its translated sentences. */
  pieces: Piece[]
  /** Evidence passages to mark, in paragraph coordinates. */
  spans: Span[]
  sessionId: number
  /** Summaries of this paragraph already kept. */
  summaries: Summary[]
  onSummary: (summary: Summary) => void
  /** Another paragraph holds the microphone. */
  active: boolean
  onStart: () => void
  onEnd: () => void
}

/**
 * One paragraph of the article in its own formatting throughout: sentences
 * flip to Korean on click, and the read-aloud marks are drawn on the words in place.
 * Read aloud and Summarize sit in one row right under the text and stay there; what
 * their rounds show goes below the row. The text stays in view while it is summed up.
 */
export function Paragraph({ paragraph, pieces, spans, sessionId, summaries, onSummary, active, onStart, onEnd }: Props) {
  const starts = useMemo(() => wordStarts(paragraph), [paragraph])
  const round = useReadAloud({ paragraph, sessionId, onStart, onEnd })
  const summary = useSummary({ paragraph, sessionId, onKept: onSummary, onStart, onEnd })
  const marks: Marks = { findings: round.findings, open: round.open, onOpen: round.ask }

  return (
    <div className="paragraph">
      <p>
        {pieces.map((piece, j) => {
          const run = { text: piece.text, start: piece.start, spans, starts, marks }
          return piece.ko === null ? <Run key={j} {...run} /> : <Sentence key={j} {...run} ko={piece.ko} />
        })}
      </p>
      <div className="paragraph-actions">
        <ReadAloudButton round={round} disabled={active || summary.state !== null} />
        <SummarizeButton summary={summary} kept={summaries.length > 0} disabled={active || round.phase !== null} />
      </div>
      <ReadAloudPanel round={round} />
      <SummaryPanel summary={summary} kept={summaries} />
    </div>
  )
}
