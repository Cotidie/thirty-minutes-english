import { useId, useState } from 'react'
import { api } from '../api'
import { creditCount, giftable } from '../lib/gifts'
import { nobodySaying, usePeopleNamed } from '../lib/usePeopleNamed'
import type { PersonMatch } from '../types'

interface Props {
  /** What there is to give. */
  balance: number
  /** Back to the charges: when Back is pressed, and once a gift has gone. */
  onClose: () => void
  /** True from the moment a gift is sent until its answer comes: the panel must stay open meanwhile. */
  onSending: (sending: boolean) => void
}

/** The credits panel's gift screen: find someone by username, say how much, and answer once before it goes. Everything
 * is drawn inside the panel, so pressing a name or the question does not count as leaving it. */
export function GiftCredits({ balance, onClose, onSending }: Props) {
  const [recipient, setRecipient] = useState<PersonMatch | null>(null)
  return (
    <div className="gift">
      <button type="button" className="btn-link gift-back" onClick={onClose}>
        Back
      </button>
      {recipient ? (
        <GiftAmount recipient={recipient} balance={balance} onGiven={onClose} onSending={onSending} />
      ) : (
        <FindRecipient onPick={setRecipient} />
      )}
    </div>
  )
}

/** A search by username, the same one sharing a session uses; whoever searches is never offered. */
function FindRecipient({ onPick }: { onPick: (person: PersonMatch) => void }) {
  const [typed, setTyped] = useState('')
  const found = usePeopleNamed(typed)
  const id = useId()
  return (
    <>
      <label className="gift-label" htmlFor={id}>
        Gift credits to
      </label>
      <input
        id={id}
        className="gift-input"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        placeholder="their username"
        autoCapitalize="none"
        spellCheck={false}
        autoFocus
      />
      {typed.trim() !== '' &&
        (found.people.length > 0 ? (
          <ul className="gift-matches" aria-label="Matches">
            {found.people.map((person) => (
              <li key={person.id}>
                <button type="button" className="gift-match" onClick={() => onPick(person)}>
                  {person.username}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="gift-none">{nobodySaying(found)}</p>
        ))}
    </>
  )
}

/** What the question asks: the amount and what is left, as they stood when it was asked, so the gift's own credits
 * event cannot change them while it is on its way. */
interface Asked {
  amount: number
  left: number
}

function GiftAmount({
  recipient,
  balance,
  onGiven,
  onSending,
}: {
  recipient: PersonMatch
  balance: number
  onGiven: () => void
  onSending: (sending: boolean) => void
}) {
  const [typed, setTyped] = useState('')
  const [asked, setAsked] = useState<Asked | null>(null)
  const amount = giftable(typed, balance)
  const id = useId()
  return (
    <>
      <h3 className="gift-title">Gift to {recipient.username}</h3>
      <label className="gift-label" htmlFor={id}>
        Credits to gift
      </label>
      <input
        id={id}
        className="gift-input"
        type="text"
        inputMode="numeric"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        autoFocus
      />
      <p className="gift-have">You have {balance}.</p>
      <button
        type="button"
        className="btn btn-primary gift-send"
        disabled={amount === null}
        onClick={() => amount !== null && setAsked({ amount, left: balance - amount })}
      >
        {amount === null ? 'Gift credits' : `Gift ${creditCount(amount)}`}
      </button>
      {asked && (
        <ConfirmGift recipient={recipient} asked={asked} onCancel={() => setAsked(null)} onGiven={onGiven} onSending={onSending} />
      )}
    </>
  )
}

/** The one question before a gift goes. While it is on its way neither answer can be given, and a refusal stays here. */
function ConfirmGift({
  recipient,
  asked,
  onCancel,
  onGiven,
  onSending,
}: {
  recipient: PersonMatch
  asked: Asked
  onCancel: () => void
  onGiven: () => void
  onSending: (sending: boolean) => void
}) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const titleId = useId()
  const bodyId = useId()

  async function send() {
    setSending(true)
    setError(null)
    onSending(true)
    try {
      await api.giftCredits(recipient.id, asked.amount)
    } catch (e) {
      setError((e as Error).message)
      setSending(false)
      onSending(false)
      return
    }
    onSending(false)
    onGiven()
  }

  return (
    <div className="gift-confirm">
      <div role="alertdialog" aria-labelledby={titleId} aria-describedby={bodyId} className="gift-confirm-card">
        <h3 id={titleId}>
          Gift {creditCount(asked.amount)} to {recipient.username}?
        </h3>
        <p id={bodyId}>You will have {asked.left} left. A gift cannot be taken back.</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="gift-confirm-actions">
          <button type="button" className="btn" disabled={sending} onClick={onCancel} autoFocus>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={sending} onClick={() => void send()}>
            Gift
          </button>
        </div>
      </div>
    </div>
  )
}
