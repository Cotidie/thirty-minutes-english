import { useState } from 'react'
import { practiceExpression, type Example, type Expression } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'

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
        For each expression: read the examples aloud, agree on when you would use it, then each of you presses Your
        turn and says one new sentence about your own week. The coach says it back the way a native speaker would and
        adds one line of feedback.
      </p>
      <ol className="expression-list">
        {items.map((item) => (
          <li key={item.phrase} className="expression">
            <div className="expression-head">
              <h3 className="expression-phrase">{item.phrase}</h3>
              <StarButton
                label={item.phrase}
                on={starred.includes(item.phrase)}
                onToggle={() => onToggleStar(item.phrase)}
              />
            </div>
            <p className="expression-meaning">{item.meaning}</p>
            <UsageNote text={item.usage_note} />
            <ul className="expression-examples">
              {item.examples.map((ex) => (
                <li key={ex}>{ex}</li>
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
