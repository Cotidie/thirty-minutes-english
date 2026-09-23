import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { practiceWord, type Example, type PictureStyles, type VocabularyItem } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'
import { KoreanChip } from './KoreanChip'
import { Synonyms } from './Synonyms'
import './VocabularyTab.css'

/** A redraw is one request (new scene, then the picture), so there is no true progress:
 * the ring creeps toward a typical wait and holds short of full. */
const REDRAW_SECONDS = 60

function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    if (!active) return
    setSeconds(0)
    const start = Date.now()
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 500)
    return () => clearInterval(timer)
  }, [active])
  return active ? seconds : 0
}

function Drawing({ seconds }: { seconds: number }) {
  const fill = Math.min(0.95, seconds / REDRAW_SECONDS)
  return (
    <span className="vocab-drawing" role="status" aria-live="polite">
      <span className="vocab-drawing-ring" style={{ '--fill': fill } as React.CSSProperties} aria-hidden="true" />
      <span className="vocab-drawing-text">
        Drawing… <b>{seconds}s</b>
      </span>
    </span>
  )
}

/** The caption with the word (in whatever form it takes there) marked. */
function Marked({ text, word }: { text: string; word: string }) {
  const stem = word.replace(/e$/, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = text.split(new RegExp(`(\\b${stem}\\w*)`, 'i'))
  return <>{parts.map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : part))}</>
}

/** Why the picture is the word: the picture blurs and the caption rises over it; a click on it closes. */
function SceneCaption({ caption, word }: { caption: string; word: string }) {
  const [shown, setShown] = useState(false)
  return (
    <>
      <span
        className={`vocab-caption${shown ? ' is-shown' : ''}`}
        role="note"
        aria-hidden={!shown}
        onClick={(e) => {
          e.stopPropagation()
          setShown(false)
        }}
      >
        <span className="vocab-caption-label">The scene</span>
        <span className="vocab-caption-text">
          <Marked text={caption} word={word} />
        </span>
      </span>
      <button
        type="button"
        className="vocab-caption-toggle"
        aria-expanded={shown}
        aria-label={shown ? `Hide the scene for ${word}` : `What the picture for ${word} shows`}
        onClick={(e) => {
          e.stopPropagation()
          setShown((s) => !s)
        }}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M2 3.5h12v7H7l-3 2.5v-2.5H2z" strokeLinejoin="round" />
        </svg>
        {shown ? 'Hide' : 'Scene'}
      </button>
    </>
  )
}

function VocabCard({ item, drawing }: { item: VocabularyItem; drawing: boolean }) {
  const [revealed, setRevealed] = useState(false)
  const seconds = useElapsed(drawing)
  return (
    <div className={`vocab-card${revealed ? ' is-revealed' : ''}`} onClick={() => setRevealed((r) => !r)}>
      {item.image && (
        <span className="vocab-picture-frame" style={{ '--picture': `url(/api/images/${item.image})` } as React.CSSProperties}>
          <img className={`vocab-picture${drawing ? ' is-drawing' : ''}`} src={`/api/images/${item.image}`} alt={item.scene ?? item.word} />
          {drawing ? <Drawing seconds={seconds} /> : item.caption && <SceneCaption key={item.image} caption={item.caption} word={item.word} />}
        </span>
      )}
      <span className="vocab-word">
        <span className="vocab-word-text">{item.word}</span> <em className="vocab-pos">{item.pos}</em>
        {item.korean && <KoreanChip korean={item.korean} of={item.word} />}
      </span>
      <span className="vocab-example">{item.example}</span>
      <button
        type="button"
        className="vocab-definition"
        aria-expanded={revealed}
        onClick={(e) => {
          e.stopPropagation()
          setRevealed((r) => !r)
        }}
      >
        {revealed ? (
          <>
            {item.definition}
            <Synonyms words={item.synonyms} />
          </>
        ) : (
          'Tap to check the meaning'
        )}
      </button>
    </div>
  )
}

interface Props {
  items: VocabularyItem[]
  sessionId: number
  /** A word's picture was redrawn; the session holds the new item. */
  onPicture: (index: number, item: VocabularyItem) => void
  starred: string[]
  onToggleStar: (word: string) => void
  /** Every sentence made in this session; each word shows its own. */
  examples: Example[]
  onExample: (example: Example) => void
}

export function VocabularyTab({ items, sessionId, onPicture, starred, onToggleStar, examples, onExample }: Props) {
  const [drawing, setDrawing] = useState<Set<number>>(new Set())
  const [failed, setFailed] = useState<Record<number, string>>({})
  const [styles, setStyles] = useState<PictureStyles>({ current: '', options: [] })
  /** The style every ↻ draws in; starts at the configured one, changes only this page. */
  const [style, setStyle] = useState('')

  useEffect(() => {
    api
      .pictureStyles()
      .then((s) => {
        setStyles(s)
        setStyle(s.current)
      })
      .catch(() => undefined)
  }, [])

  /** A new scene and picture for one word, in place, in the style picked above the cards. */
  const redraw = async (index: number) => {
    setDrawing((d) => new Set(d).add(index))
    setFailed(({ [index]: _, ...rest }) => rest)
    try {
      onPicture(index, await api.redrawPicture(sessionId, index, style))
    } catch (e) {
      setFailed((f) => ({ ...f, [index]: e instanceof Error ? e.message : String(e) }))
    } finally {
      setDrawing((d) => {
        const next = new Set(d)
        next.delete(index)
        return next
      })
    }
  }

  return (
    <section className="tab-panel is-wide">
      <p className="tab-brief">
        Take turns. Read the word and its sentence aloud, then explain in English what you think it means. Check only
        after both of you have tried.
      </p>
      {styles.options.length > 0 && (
        <div className="vocab-style-bar" role="radiogroup" aria-label="Style for new pictures">
          <span className="vocab-style-label">↻ redraws in</span>
          {styles.options.map((o) => (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={o.id === style}
              title={o.description}
              className="vocab-style"
              onClick={() => setStyle(o.id)}
            >
              {o.description || o.id}
            </button>
          ))}
        </div>
      )}
      <div className="vocab-grid">
        {items.map((item, index) => (
          <div key={item.word} className={`vocab-cell${item.image ? '' : ' is-bare'}`}>
            <VocabCard item={item} drawing={drawing.has(index)} />
            <StarButton label={item.word} on={starred.includes(item.word)} onToggle={() => onToggleStar(item.word)} />
            {item.scene && (
              <button
                type="button"
                className="vocab-redraw"
                aria-label={`New picture for ${item.word}`}
                title={drawing.has(index) ? 'Drawing…' : `New scene, new picture${style ? ` (${style})` : ''}`}
                disabled={drawing.has(index)}
                onClick={() => void redraw(index)}
              >
                {drawing.has(index) ? '…' : '↻'}
              </button>
            )}
            {failed[index] && <p className="vocab-redraw-error">{failed[index]}</p>}
            <Practice
              target={practiceWord(item)}
              label="Practice"
              sessionId={sessionId}
              examples={examples.filter((e) => e.expression === item.word)}
              onKept={onExample}
            />
          </div>
        ))}
      </div>
    </section>
  )
}
