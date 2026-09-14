import { useState, type KeyboardEvent } from 'react'
import type { Segment } from '../lib/highlight'

type Phase = 'still' | 'sinking' | 'rising'

interface Props {
  segments: Segment[]
  ko: string
}

/**
 * One sentence of the article. A click sinks the English and floats the
 * Korean up in its place; another click brings the English back.
 */
export function Sentence({ segments, ko }: Props) {
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
      {lang === 'en' ? <Run segments={segments} /> : ko}
    </span>
  )
}

/** Plain article text with any evidence passage marked. */
export function Run({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map((seg, j) => (seg.marked ? <mark key={j}>{seg.text}</mark> : <span key={j}>{seg.text}</span>))}
    </>
  )
}
