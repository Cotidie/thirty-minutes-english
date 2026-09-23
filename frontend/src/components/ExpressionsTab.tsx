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
  starred: string[]
  onToggleStar: (phrase: string) => void
  /** Every sentence made in this session; each expression shows its own. */
  examples: Example[]
  onExample: (example: Example) => void
}

export function ExpressionsTab({ items, sessionId, starred, onToggleStar, examples, onExample }: Props) {
  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Read the examples aloud, then each of you makes one sentence of your own. Press Your turn to have it echoed back
        the native way.
      </p>
      <ol className="expression-list">
        {items.map((item) => (
          <li key={item.phrase} className="expression">
            <div className="expression-head">
              <h3 className="expression-phrase">{item.phrase}</h3>
              {item.korean && <KoreanChip korean={item.korean} of={item.phrase} />}
              <StarButton
                label={item.phrase}
                on={starred.includes(item.phrase)}
                onToggle={() => onToggleStar(item.phrase)}
              />
            </div>
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
              examples={examples.filter((e) => e.expression === item.phrase)}
              onKept={onExample}
            />
          </li>
        ))}
      </ol>
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
