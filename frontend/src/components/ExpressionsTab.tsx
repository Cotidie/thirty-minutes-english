import { useState } from 'react'
import { practiceExpression, type Example, type Expression } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'
import { KoreanChip } from './KoreanChip'
import { Synonyms } from './Synonyms'
import { Marked } from './Marked'
import './ExpressionsTab.css'

interface Props {
  items: Expression[]
  sessionId: number
  /** Ids of the starred expressions. */
  starred: number[]
  onToggleStar: (id: number) => void
  /** Every sentence made in this session; each expression shows its own. */
  examples: Example[]
  onExample: (example: Example) => void
  /** Puts another corpus expression in this one's place; rejects with what went wrong. */
  onSwap: (id: number) => Promise<void>
  /** Teaches one more corpus expression after the others; rejects with what went wrong. */
  onAdd: () => Promise<void>
}

/** What a failed change was about: an expression's swap, or the add. */
type Failure = { at: number | 'add'; message: string }

export function ExpressionsTab({ items, sessionId, starred, onToggleStar, examples, onExample, onSwap, onAdd }: Props) {
  // One change at a time, so two at once cannot pick the same expression.
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)

  async function change(at: Failure['at'], run: () => Promise<void>) {
    setBusy(true)
    setFailure(null)
    try {
      await run()
    } catch (e) {
      setFailure({ at, message: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const add = (
    <>
      <button
        type="button"
        className="expression-add"
        aria-label="Add another expression"
        title="Add another expression"
        disabled={busy}
        onClick={() => void change('add', onAdd)}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
          <path d="M10 4v12M4 10h12" />
        </svg>
      </button>
      {failure?.at === 'add' && <p className="error">Could not add one: {failure.message}</p>}
    </>
  )

  if (items.length === 0) {
    return (
      <section className="tab-panel">
        <p className="empty">This session has no expressions.</p>
        {add}
      </section>
    )
  }
  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read the examples aloud, then each of you makes one sentence of your own. Press Your turn to have it echoed back
        the native way.
      </p>
      <ol className="expression-list">
        {items.map((item) => (
          <li key={item.id} className="expression">
            <div className="expression-head">
              <h3 className="expression-phrase">{item.phrase}</h3>
              {item.korean && <KoreanChip korean={item.korean} of={item.phrase} />}
              <button
                type="button"
                className="expression-swap"
                aria-label={`Swap ${item.phrase} for another expression`}
                title="Swap for another expression"
                disabled={busy}
                onClick={() => void change(item.id, () => onSwap(item.id))}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M13.5 8a5.5 5.5 0 0 1-9.7 3.6M2.5 8a5.5 5.5 0 0 1 9.7-3.6" />
                  <path d="M12.6 1.6v2.8H9.8M3.4 14.4v-2.8h2.8" />
                </svg>
              </button>
              <StarButton
                label={item.phrase}
                on={starred.includes(item.id)}
                onToggle={() => onToggleStar(item.id)}
              />
            </div>
            {failure?.at === item.id && <p className="error">Could not swap it: {failure.message}</p>}
            <p className="expression-meaning">
              {item.meaning}
              <Synonyms words={item.synonyms} />
            </p>
            <UsageNote text={item.usage_note} />
            <ul className="expression-examples">
              {item.examples.map((ex) => (
                <li key={ex}>
                  <Marked text={ex} word={item.phrase} />
                </li>
              ))}
            </ul>
            <Practice
              target={practiceExpression(item)}
              label="Your turn: one sentence each."
              sessionId={sessionId}
              examples={examples.filter((e) => e.expression_id === item.id)}
              onKept={onExample}
            />
          </li>
        ))}
      </ol>
      {add}
    </section>
  )
}

function UsageNote({ text }: { text: string }) {
  const [clamped, setClamped] = useState(true)
  return (
    <button
      type="button"
      className={`expression-note${clamped ? ' is-clamped' : ''}`}
      title={clamped ? 'Show the full note' : 'Shorten the note'}
      onClick={() => setClamped((c) => !c)}
    >
      {text}
    </button>
  )
}
