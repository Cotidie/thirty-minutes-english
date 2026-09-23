import type { ReactNode } from 'react'
import type { Ask } from '../types'
import './AskCard.css'

interface Props {
  asked: ReactNode
  /** The marked line. Missing means the round left no answer. */
  english?: string
  alternatives?: string[]
  note?: ReactNode
}

/** One ledger row: what was said in the margin, the English marked in the column. */
export function AskCard({ asked, english, alternatives = [], note }: Props) {
  return (
    <li className="ask-card">
      <p className="ask-card-asked">{asked}</p>
      <div className="ask-card-body">
        {english ? (
          <p className="ask-card-english">
            <mark>{english}</mark>
          </p>
        ) : (
          <p className="ask-card-english is-missing">No answer landed in this round.</p>
        )}
        {alternatives.map((alt) => (
          <p key={alt} className="ask-card-alt">
            {alt}
          </p>
        ))}
        {note && <p className="ask-card-note">{note}</p>}
      </div>
    </li>
  )
}

export function AskedCard({ ask }: { ask: Ask }) {
  return (
    <AskCard
      asked={ask.card?.asked || ask.user_text}
      english={ask.card?.english}
      alternatives={ask.card?.alternatives}
      note={ask.card?.note}
    />
  )
}
