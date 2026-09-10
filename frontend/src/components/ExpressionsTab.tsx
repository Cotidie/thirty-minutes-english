import { useState } from 'react'
import type { Expression } from '../types'

export function ExpressionsTab({ items }: { items: Expression[] }) {
  return (
    <section className="tab-panel">
      <p className="tab-brief">
        For each expression: read the examples aloud, agree on when you would use it, then each of you makes one new
        sentence about your own week.
      </p>
      <ol className="expression-list">
        {items.map((item) => (
          <li key={item.phrase} className="expression">
            <h3 className="expression-phrase">{item.phrase}</h3>
            <p className="expression-meaning">{item.meaning}</p>
            <UsageNote text={item.usage_note} />
            <ul className="expression-examples">
              {item.examples.map((ex) => (
                <li key={ex}>{ex}</li>
              ))}
            </ul>
            <p className="your-turn">Your turn: one sentence each.</p>
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
