import { useCallback, useRef, useState } from 'react'
import { useCloseOnLeave } from '../lib/useCloseOnLeave'
import { useCredits } from '../lib/credits'
import type { CreditEntry } from '../types'
import './CreditsPill.css'

const KIND_LABELS: Record<string, string> = {
  refund: 'Refund',
  session: 'Session',
  session_cancelled: 'Cancelled session',
  redraw: 'New picture',
  practice_voice: 'Practice',
  practice_feedback: 'Practice feedback',
  summary_voice: 'Summarize',
  summary_feedback: 'Summary feedback',
  read_aloud_token: 'Read aloud',
  read_aloud_voice: 'Coach',
  speech: 'Sentence',
}

/** A coin and what is left to spend; pressing it opens the last charges. */
export function CreditsPill() {
  const { balance, recent } = useCredits()
  const [open, setOpen] = useState(false)
  const here = useRef<HTMLDivElement>(null)
  const close = useCallback(() => setOpen(false), [])
  useCloseOnLeave(open, here, close)

  if (balance === null) return null
  const short = balance < 0 ? ' is-short' : ''
  return (
    <div className="credits" ref={here}>
      <button
        type="button"
        className={`corner-button credits-pill${short}`}
        aria-label="Credits"
        aria-expanded={open}
        title="Credits"
        onClick={() => setOpen((was) => !was)}
      >
        <span className="credits-coin" aria-hidden="true" />
        {balance}
      </button>
      {open && (
        <div className="credits-panel" role="dialog" aria-label="Credits">
          <p className={`credits-balance${short}`}>
            <span className="credits-coin" aria-hidden="true" />
            {balance}
          </p>
          {recent.length > 0 ? (
            <ul className="credit-lines" aria-label="Recent charges">
              {recent.map((entry, i) => (
                <CreditLine key={i} entry={entry} />
              ))}
            </ul>
          ) : (
            <p className="credits-none">No charges yet.</p>
          )}
          <p className="credits-more">Ask the admin for more.</p>
        </div>
      )}
    </div>
  )
}

/** One line of an account's history. `grantedBy` names who adds credits or takes them back, as the reader knows them. */
export function CreditLine({ entry, grantedBy = 'the admin' }: { entry: CreditEntry; grantedBy?: string }) {
  const label = entry.kind === 'grant' ? `${entry.amount < 0 ? 'Taken back' : 'Added'} by ${grantedBy}` : (KIND_LABELS[entry.kind] ?? entry.kind)
  return (
    <li className="credit-line">
      <time dateTime={entry.at}>{new Date(entry.at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time>
      <span className="credit-what">
        {label}
        {entry.detail && <span className="credit-detail"> · {entry.detail}</span>}
      </span>
      <span className="credit-amount">{entry.amount > 0 ? `+${entry.amount}` : `−${-entry.amount}`}</span>
    </li>
  )
}
