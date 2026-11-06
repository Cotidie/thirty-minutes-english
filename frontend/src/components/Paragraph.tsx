import { useMemo } from 'react'
import type { Shown } from '../lib/assessor/judge'
import type { Span } from '../lib/highlight'
import type { Piece } from '../lib/sentences'
import type { Paragraph as ArticleParagraph, Reading, Summary } from '../types'
import { useOthersRound, useSomeoneReading } from '../lib/presence/useSharedRound'
import { usePrice } from '../lib/usePrice'
import { wordStarts, type Marks } from '../lib/words'
import { ReadAloudButton, ReadAloudPanel, useReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'
import { SummarizeButton, SummaryPanel, useSummary } from './Summarize'
import './Paragraph.css'

interface Props {
  paragraph: ArticleParagraph
  /** The paragraph cut into its translated sentences. */
  pieces: Piece[]
  /** Evidence passages to mark, in paragraph coordinates. */
  spans: Span[]
  /** Summaries of this paragraph already kept. */
  summaries: Summary[]
  /** The marks this paragraph's last read-aloud round left. */
  saved: Shown[]
  onSummary: (summary: Summary) => void
  /** A round read on this page is filed. */
  onReading: (reading: Reading) => void
  /** Another paragraph holds the microphone. */
  active: boolean
  onStart: () => void
  onEnd: () => void
}

/**
 * One paragraph of the article in its own formatting throughout: sentences
 * flip to Korean on click, and the read-aloud marks are drawn on the words in place.
 * Read aloud and Summarize sit in one row right under the text and stay there; what
 * their rounds show goes below the row. The text stays in view while it is summed up. Someone else's round on it shows
 * here as they read, and while anyone reads, no one else starts a round.
 */
export function Paragraph({ paragraph, pieces, spans, summaries, saved, onSummary, onReading, active, onStart, onEnd }: Props) {
  const starts = useMemo(() => wordStarts(paragraph.text), [paragraph.text])
  const watched = useOthersRound(paragraph.id)
  const reader = useSomeoneReading()
  const round = useReadAloud({ paragraph, saved: watched?.round.findings ?? saved, onFiled: onReading, onStart, onEnd })
  const summary = useSummary({ paragraph, onKept: onSummary, onStart, onEnd })
  const coach = usePrice('read_aloud_voice')
  const marks: Marks = { findings: round.findings, open: round.open, onOpen: round.ask, locked: coach.short, price: coach.price }

  return (
    <div className="paragraph" data-presence-anchor={`paragraph:${paragraph.id}`}>
      <p>
        {pieces.map((piece, j) => {
          const run = { text: piece.text, start: piece.start, spans, starts, marks }
          return piece.ko === null ? <Run key={j} {...run} /> : <Sentence key={j} {...run} ko={piece.ko} viewKey={`sentence:${paragraph.id}:${piece.start}`} />
        })}
      </p>
      <div className="paragraph-actions">
        <ReadAloudButton round={round} disabled={active || summary.state !== null} reader={reader} />
        <SummarizeButton summary={summary} kept={summaries.length > 0} disabled={active || round.phase !== null} reader={reader} />
      </div>
      <ReadAloudPanel round={round} watched={watched} />
      <SummaryPanel summary={summary} kept={summaries} />
    </div>
  )
}
