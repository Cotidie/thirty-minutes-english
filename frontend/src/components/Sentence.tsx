import { Fragment, useState, type KeyboardEvent } from 'react'
import { segmentsIn, type Span } from '../lib/highlight'
import { atoms, type Atom, type Marks } from '../lib/words'
import './Sentence.css'

type Phase = 'still' | 'sinking' | 'rising'

export interface RunProps {
  text: string
  /** Where `text` starts in its paragraph. */
  start: number
  /** Evidence passages, in paragraph coordinates. */
  spans: Span[]
  /** Word index by paragraph offset, from `wordStarts`. */
  starts: Map<number, number>
  marks: Marks
}

/**
 * One sentence of the article. A click sinks the English and floats the
 * Korean up in its place; another click brings the English back.
 */
export function Sentence({ ko, ...run }: RunProps & { ko: string }) {
  const [lang, setLang] = useState<'en' | 'ko'>('en')
  const [phase, setPhase] = useState<Phase>('still')

  const flip = () => {
    if (phase === 'still') setPhase('sinking')
  }
  const onAnimationEnd = () => {
    if (phase === 'sinking') {
      setLang((l) => (l === 'en' ? 'ko' : 'en'))
      setPhase('rising')
    } else if (phase === 'rising') {
      setPhase('still')
    }
  }
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      flip()
    }
  }

  return (
    <span
      role="button"
      tabIndex={0}
      className={`swap is-${lang} is-${phase}`}
      lang={lang === 'ko' ? 'ko' : undefined}
      title={lang === 'en' ? '한국어로 보기' : 'Back to the English'}
      onClick={flip}
      onKeyDown={onKeyDown}
      onAnimationEnd={onAnimationEnd}
    >
      {lang === 'en' ? <Run {...run} /> : ko}
    </span>
  )
}

/** Article text word by word: evidence marked, findings on their words. */
export function Run({ text, start, spans, starts, marks }: RunProps) {
  return (
    <>
      {atoms(text, start, starts).map((atom, j) => (
        <Word key={j} atom={atom} spans={spans} marks={marks} />
      ))}
    </>
  )
}

/** A mispronounced word is a button that opens its finding. Green once read right. */
function Word({ atom, spans, marks }: { atom: Atom; spans: Span[]; marks: Marks }) {
  const inner = segmentsIn(atom.text, spans, atom.offset).map((seg, j) =>
    seg.marked ? <mark key={j}>{seg.text}</mark> : <Fragment key={j}>{seg.text}</Fragment>,
  )
  const index = atom.word === null ? -1 : marks.findings.findIndex((f) => f.at === atom.word)
  if (index < 0) return <>{inner}</>
  const finding = marks.findings[index]
  const title = `${finding.word}: ${finding.heard}`
  return (
    <button
      type="button"
      className={`reading-hit${finding.repeated_ok ? ' is-ok' : ''}${marks.open === index ? ' is-open' : ''}`}
      title={title}
      aria-label={title}
      onClick={() => marks.onOpen(index)}
    >
      {inner}
    </button>
  )
}
