import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { practiceWord, type Example, type PictureStyles, type VocabularyItem } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'
import { KoreanChip } from './KoreanChip'
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

function VocabCard({ item, drawing }: { item: VocabularyItem; drawing: boolean }) {
  const [revealed, setRevealed] = useState(false)
  const seconds = useElapsed(drawing)
  return (
    <div className={`vocab-card${revealed ? ' is-revealed' : ''}`} onClick={() => setRevealed((r) => !r)}>
      {item.image && (
        <span className="vocab-picture-frame">
          <img className={`vocab-picture${drawing ? ' is-drawing' : ''}`} src={`/api/images/${item.image}`} alt={item.scene ?? item.word} />
          {drawing && <Drawing seconds={seconds} />}
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
        {revealed ? item.definition : 'Tap to check the meaning'}
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
  /** The cell whose style menu is open. */
  const [menu, setMenu] = useState<number | null>(null)
  const [styles, setStyles] = useState<PictureStyles>({ current: '', choices: [], labels: {} })

  useEffect(() => {
    api.pictureStyles().then(setStyles).catch(() => undefined)
  }, [])

  /** A new scene and picture for one word, in place, in the chosen style. */
  const redraw = async (index: number, style: string) => {
    setMenu(null)
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
      <div className="vocab-grid">
        {items.map((item, index) => (
          <div key={item.word} className="vocab-cell">
            <VocabCard item={item} drawing={drawing.has(index)} />
            <StarButton label={item.word} on={starred.includes(item.word)} onToggle={() => onToggleStar(item.word)} />
            {item.scene && (
              <button
                type="button"
                className="vocab-redraw"
                aria-label={`New picture for ${item.word}`}
                aria-expanded={menu === index}
                title={drawing.has(index) ? 'Drawing…' : 'New scene, new picture'}
                disabled={drawing.has(index)}
                onClick={() => setMenu(menu === index ? null : index)}
              >
                {drawing.has(index) ? '…' : '↻'}
              </button>
            )}
            {menu === index && (
              <ul className="vocab-styles" role="menu" aria-label={`Picture style for ${item.word}`}>
                {(styles.choices.length > 0 ? styles.choices : ['']).map((style) => (
                  <li key={style}>
                    <button type="button" role="menuitem" onClick={() => void redraw(index, style)}>
                      {style ? `${style}${styles.labels[style] ? ` · ${styles.labels[style]}` : ''}` : 'Draw again'}
                      {style && style === styles.current ? ' (current)' : ''}
                    </button>
                  </li>
                ))}
              </ul>
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
