import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { practiceWord, type Example, type PictureFace, type PictureStyles, type VocabularyItem } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'
import { KoreanChip } from './KoreanChip'
import { Synonyms } from './Synonyms'
import { Marked } from './Marked'
import { SpeakButton } from './SpeakButton'
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

/** The word's two pictures, one at a time: the example sentence drawn, and behind the flip
 * button the scene to describe in Practice, which alone carries the Scene caption. */
interface PictureProps {
  item: VocabularyItem
  face: PictureFace
  onFlip: () => void
  /** A redraw of this word is under way. */
  drawing: boolean
  /** The session's first pictures are still landing; a face without one is waiting for its own. */
  arriving: boolean
}

function VocabPicture({ item, face, onFlip, drawing, arriving }: PictureProps) {
  const seconds = useElapsed(drawing)
  const practice = face === 'practice'
  const image = practice ? item.image : item.example_image
  return (
    <span className="vocab-picture-frame">
      {image ? (
        <img
          className={`vocab-picture${drawing ? ' is-drawing' : ''}`}
          src={`/api/images/${image}`}
          alt={practice ? (item.scene ?? item.word) : item.example}
        />
      ) : (
        <span className="vocab-picture is-empty">{!drawing && (arriving ? 'Drawing…' : 'No picture yet. ↻ draws one.')}</span>
      )}
      {drawing ? (
        <Drawing seconds={seconds} />
      ) : (
        practice && image && item.caption && <SceneCaption key={image} caption={item.caption} word={item.word} />
      )}
      <button
        type="button"
        className="vocab-flip"
        aria-label={`Show the ${practice ? 'example' : 'practice'} picture for ${item.word}`}
        onClick={(e) => {
          e.stopPropagation()
          onFlip()
        }}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M3 6h10l-3-3M13 10H3l3 3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {practice ? 'Example' : 'Practice'}
      </button>
    </span>
  )
}

function VocabCard({ item, picture }: { item: VocabularyItem; picture: React.ReactNode }) {
  const [revealed, setRevealed] = useState(false)
  return (
    <div className={`vocab-card${revealed ? ' is-revealed' : ''}`} onClick={() => setRevealed((r) => !r)}>
      {picture}
      <span className="vocab-word">
        <span className="vocab-word-text">{item.word}</span> <em className="vocab-pos">{item.pos}</em>
        <SpeakButton text={item.word} what={item.word} />
        {item.korean && <KoreanChip korean={item.korean} of={item.word} />}
      </span>
      <span className="vocab-example">
        <Marked text={item.example} word={item.word} />
        <SpeakButton text={item.example} />
      </span>
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

interface CellProps {
  item: VocabularyItem
  drawing: boolean
  arriving: boolean
  /** Why the last redraw failed. */
  failed?: string
  /** The style a redraw draws in, for the button's hint. */
  style: string
  onRedraw: (face: PictureFace) => void
  children: React.ReactNode
}

/** One word: its card, with the picture face it shows, and the redraw button for that face. */
function VocabCell({ item, drawing, arriving, failed, style, onRedraw, children }: CellProps) {
  /** The face the learner flipped to; until then the example, wherever one is drawn or on its way. */
  const [flipped, setFlipped] = useState<PictureFace | null>(null)
  const face = flipped ?? (item.example_image || arriving ? 'example' : 'practice')
  const pictured = Boolean(item.image || item.example_image || arriving)
  const hint = face === 'example' ? 'The example sentence, drawn again' : 'New scene, new picture'
  return (
    <div className={`vocab-cell${pictured ? '' : ' is-bare'}`}>
      <VocabCard
        item={item}
        picture={pictured && <VocabPicture item={item} face={face} onFlip={() => setFlipped(face === 'example' ? 'practice' : 'example')} drawing={drawing} arriving={arriving} />}
      />
      {(item.scene || face === 'example') && (
        <button
          type="button"
          className="vocab-redraw"
          aria-label={`New picture for ${item.word}`}
          title={drawing ? 'Drawing…' : `${hint}${style ? ` (${style})` : ''}`}
          disabled={drawing}
          onClick={() => onRedraw(face)}
        >
          {drawing ? '…' : '↻'}
        </button>
      )}
      {failed && <p className="vocab-redraw-error">{failed}</p>}
      {children}
    </div>
  )
}

interface Props {
  items: VocabularyItem[]
  sessionId: number
  /** The session's first pictures are still being drawn. */
  arriving?: boolean
  /** A word's picture was redrawn; the session holds the new item. */
  onPicture: (index: number, item: VocabularyItem) => void
  starred: string[]
  onToggleStar: (word: string) => void
  /** Every sentence made in this session; each word shows its own. */
  examples: Example[]
  onExample: (example: Example) => void
}

export function VocabularyTab({ items, sessionId, arriving = false, onPicture, starred, onToggleStar, examples, onExample }: Props) {
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

  /** One of a word's pictures again, in place, in the style picked above the cards. */
  const redraw = async (index: number, face: PictureFace) => {
    setDrawing((d) => new Set(d).add(index))
    setFailed(({ [index]: _, ...rest }) => rest)
    try {
      onPicture(index, await api.redrawPicture(sessionId, index, face, style))
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
          <VocabCell
            key={item.word}
            item={item}
            drawing={drawing.has(index)}
            arriving={arriving}
            failed={failed[index]}
            style={style}
            onRedraw={(face) => void redraw(index, face)}
          >
            <StarButton label={item.word} on={starred.includes(item.word)} onToggle={() => onToggleStar(item.word)} />
            <Practice
              target={practiceWord(item)}
              label="Practice"
              sessionId={sessionId}
              examples={examples.filter((e) => e.expression === item.word)}
              onKept={onExample}
            />
          </VocabCell>
        ))}
      </div>
    </section>
  )
}
