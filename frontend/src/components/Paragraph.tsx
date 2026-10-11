import { useMemo, useState } from 'react'
import type { Span } from '../lib/highlight'
import type { LiveState } from '../lib/liveSession'
import type { Piece } from '../lib/sentences'
import type { Summary } from '../types'
import { wordStarts, type Marks } from '../lib/words'
import { ReadAloudBar, useReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'
import { Summarize } from './Summarize'
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
 * While the reader sums it up out loud the text is veiled, so they say what they
 * understood instead of reading it back; a click lifts the veil.
 */
export function Paragraph({ paragraph, pieces, spans, sessionId, summaries, onSummary, active, onStart, onEnd }: Props) {
  const [summing, setSumming] = useState<LiveState['status'] | null>(null)
  const [peeked, setPeeked] = useState(false)
  const veiled = (summing === 'connecting' || summing === 'listening') && !peeked
  const onStatus = useMemo(
    () => (status: LiveState['status'] | null) => {
      setSumming((before) => {
        if (before === null && status !== null) onStart()
        if (before !== null && status === null) onEnd()
        return status
      })
      if (status === null) setPeeked(false)
    },
    [onStart, onEnd],
  )
  const starts = useMemo(() => wordStarts(paragraph), [paragraph])
  const round = useReadAloud({ paragraph, sessionId, onStart, onEnd })
  const marks: Marks = { findings: round.findings, open: round.open, onOpen: round.ask }

  return (
    <div className="paragraph">
      <p className={veiled ? 'is-veiled' : undefined} title={veiled ? 'Click to peek' : undefined} onClick={veiled ? () => setPeeked(true) : undefined}>
        {pieces.map((piece, j) => {
          const run = { text: piece.text, start: piece.start, spans, starts, marks }
          return piece.ko === null ? <Run key={j} {...run} /> : <Sentence key={j} {...run} ko={piece.ko} />
        })}
      </p>
      <div className="paragraph-tools">
        <ReadAloudBar round={round} active={active || summing !== null} />
        <Summarize
          paragraph={paragraph}
          sessionId={sessionId}
          kept={summaries}
          onKept={onSummary}
          disabled={active || round.phase !== null}
          onStatus={onStatus}
        />
      </div>
    </div>
  )
}
