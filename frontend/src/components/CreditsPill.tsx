import { useCallback, useRef, useState } from 'react'
import { useCloseOnLeave } from '../lib/useCloseOnLeave'
import { useCredits } from '../lib/credits'
import type { CreditEntry } from '../types'
import { GiftCredits } from './GiftCredits'
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

/** A coin and what is left to spend; pressing it opens the last charges, and from there a gift to someone else, in the
 * same panel. While a gift is on its way the panel stays open, so its answer has somewhere to land. */
export function CreditsPill() {
  const { balance, recent } = useCredits()
  const [open, setOpen] = useState(false)
  const [gifting, setGifting] = useState(false)
  const [sending, setSending] = useState(false)
  const here = useRef<HTMLDivElement>(null)
  const close = useCallback(() => {
    setOpen(false)
    setGifting(false)
  }, [])
  useCloseOnLeave(open && !sending, here, close)

  function toggle() {
    if (sending) return
    if (open) close()
    else setOpen(true)
  }

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
        onClick={toggle}
      >
        <span className="credits-coin" aria-hidden="true" />
        {balance}
      </button>
      {open && (
        <div className="credits-panel" role="dialog" aria-label="Credits">
          {gifting ? (
            <GiftCredits balance={balance} onClose={() => setGifting(false)} onSending={setSending} />
          ) : (
            <Charges balance={balance} recent={recent} onGift={() => setGifting(true)} />
          )}
        </div>
      )}
    </div>
  )
}

/** The panel's first screen: the balance, the last charges, and the way to more or to giving some away. */
function Charges({ balance, recent, onGift }: { balance: number; recent: CreditEntry[]; onGift: () => void }) {
  const short = balance < 0 ? ' is-short' : ''
  return (
    <>
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
      <button type="button" className="btn credits-gift" disabled={balance <= 0} onClick={onGift}>
        Gift credits
      </button>
    </>
  )
}

/** Kinds whose label already names the other account, so the detail is not repeated after it. */
const NAMED_KINDS = new Set(['gift_sent', 'gift_received'])

/** What a line says it was. `grantedBy` names who adds credits or takes them back, as the reader knows them. */
function lineLabel(entry: CreditEntry, grantedBy: string): string {
  if (entry.kind === 'gift_sent') return `Gift to ${entry.detail}`
  if (entry.kind === 'gift_received') return `Gift from ${entry.detail}`
  if (entry.kind === 'grant') return `${entry.amount < 0 ? 'Taken back' : 'Added'} by ${grantedBy}`
  return KIND_LABELS[entry.kind] ?? entry.kind
}

/** One line of an account's history. `grantedBy` names who adds credits or takes them back, as the reader knows them. */
export function CreditLine({ entry, grantedBy = 'the admin' }: { entry: CreditEntry; grantedBy?: string }) {
  const showDetail = entry.detail && !NAMED_KINDS.has(entry.kind)
  return (
    <li className="credit-line">
      <time dateTime={entry.at}>{new Date(entry.at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time>
      <span className="credit-what">
        {lineLabel(entry, grantedBy)}
        {showDetail && <span className="credit-detail"> · {entry.detail}</span>}
      </span>
      <span className="credit-amount">{entry.amount > 0 ? `+${entry.amount}` : `−${-entry.amount}`}</span>
    </li>
  )
}
