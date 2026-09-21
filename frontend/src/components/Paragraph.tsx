import { useMemo, useState } from 'react'
import { api } from '../api'
import type { Span } from '../lib/highlight'
import type { Piece } from '../lib/sentences'
import { wordStarts, type Marks } from '../lib/words'
import { ReadAloudBar, useReadAloud } from './ReadAloud'
import { Run, Sentence } from './Sentence'

/** The paragraph's slashes: asked for, shown or hidden. */
interface Phrasing {
  on: boolean
  breaks?: number[]
  loading?: boolean
  error?: string
}

interface Props {
  paragraph: string
  /** The paragraph cut into its translated sentences. */
  pieces: Piece[]
  /** Evidence passages to mark, in paragraph coordinates. */
  spans: Span[]
  sessionId: number | null
  /** Another paragraph holds the microphone. */
  active: boolean
  onStart: () => void
  onEnd: () => void
}

/**
 * One paragraph of the article in its own formatting throughout: sentences
 * flip to Korean on click, and the phrasing slashes and read-aloud marks are
 * drawn on the words in place.
 */
export function Paragraph({ paragraph, pieces, spans, sessionId, active, onStart, onEnd }: Props) {
  const [phrasing, setPhrasing] = useState<Phrasing>({ on: false })
  const starts = useMemo(() => wordStarts(paragraph), [paragraph])
  const round = useReadAloud({ paragraph, breaks: phrasing.breaks ?? [], sessionId, onStart, onEnd })
  const marks: Marks = {
    breaks: phrasing.on ? (phrasing.breaks ?? []) : [],
    findings: round.findings,
    open: round.open,
    onOpen: round.ask,
  }

  /** Slashes on or off; the first time asks the backend where they go. */
  const togglePhrasing = async () => {
    if (phrasing.breaks) return setPhrasing({ ...phrasing, on: !phrasing.on })
    setPhrasing({ on: true, loading: true })
    try {
      const { breaks } = await api.phrasing(paragraph)
      setPhrasing({ on: true, breaks })
    } catch (e) {
      setPhrasing({ on: false, error: e instanceof Error ? e.message : String(e) })
    }
  }

  return (
    <div className="paragraph">
      <p>
        {pieces.map((piece, j) => {
          const run = { text: piece.text, start: piece.start, spans, starts, marks }
          return piece.ko === null ? <Run key={j} {...run} /> : <Sentence key={j} {...run} ko={piece.ko} />
        })}
      </p>
      <div className="paragraph-tools">
        <button
          type="button"
          className={`phrasing-toggle${phrasing.on ? ' is-on' : ''}`}
          aria-pressed={phrasing.on}
          disabled={phrasing.loading}
          onClick={() => void togglePhrasing()}
        >
          {phrasing.loading ? 'Marking…' : 'Phrasing'}
        </button>
        {phrasing.error && <span className="phrasing-error">{phrasing.error}</span>}
        <ReadAloudBar round={round} active={active} />
      </div>
    </div>
  )
}
