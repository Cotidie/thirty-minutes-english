import { useMemo } from 'react'
import type { Span } from '../lib/highlight'
import type { Piece } from '../lib/sentences'
import { wordStarts, type Marks } from '../lib/words'
import { ReadAloudBar, useReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'
import './Paragraph.css'

interface Props {
  paragraph: string
  /** The paragraph cut into its translated sentences. */
  pieces: Piece[]
  /** Evidence passages to mark, in paragraph coordinates. */
  spans: Span[]
  sessionId: number
  /** Another paragraph holds the microphone. */
  active: boolean
  onStart: () => void
  onEnd: () => void
}

/**
 * One paragraph of the article in its own formatting throughout: sentences
 * flip to Korean on click, and the read-aloud marks are drawn on the words in place.
 */
export function Paragraph({ paragraph, pieces, spans, sessionId, active, onStart, onEnd }: Props) {
  const starts = useMemo(() => wordStarts(paragraph), [paragraph])
  const round = useReadAloud({ paragraph, sessionId, onStart, onEnd })
  const marks: Marks = { findings: round.findings, open: round.open, onOpen: round.ask }

  return (
    <div className="paragraph">
      <p>
        {pieces.map((piece, j) => {
          const run = { text: piece.text, start: piece.start, spans, starts, marks }
          return piece.ko === null ? <Run key={j} {...run} /> : <Sentence key={j} {...run} ko={piece.ko} />
        })}
      </p>
      <ReadAloudBar round={round} active={active} />
    </div>
  )
}
