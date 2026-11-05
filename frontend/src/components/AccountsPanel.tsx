import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Account, CreditEntry } from '../types'
import { CreditLine } from './CreditsPill'
import './AccountsPanel.css'

/** Who signed up, what each has to spend, and what each spent it on. A grant saves at once. */
export function AccountsPanel() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    api
      .listAccounts()
      .then((a) => live && setAccounts(a))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [])

  const replace = (saved: Account) => setAccounts((all) => all.map((a) => (a.id === saved.id ? saved : a)))

  return (
    <div className="accounts">
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ul className="accounts-list">
        {accounts.map((account) => (
          <li key={account.id} className="accounts-item">
            <span className="accounts-who">
              <span className="accounts-email">{account.email}</span>
              <span className="accounts-name">{account.username}</span>
              <time className="accounts-joined" dateTime={account.created_at}>
                Joined {new Date(account.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
              </time>
            </span>
            {account.credits === null ? <NotCharged /> : <Charged account={account} credits={account.credits} onSaved={replace} onError={setError} />}
          </li>
        ))}
      </ul>
    </div>
  )
}

function NotCharged() {
  return (
    <span className="accounts-credits">
      <span className="accounts-balance">∞</span>
      <small>not charged</small>
    </span>
  )
}

interface ChargedProps {
  account: Account
  credits: number
  onSaved: (account: Account) => void
  onError: (error: string | null) => void
}

/** The balance, the field to change it, and the account's last charges under them. */
function Charged({ account, credits, onSaved, onError }: ChargedProps) {
  const [amount, setAmount] = useState('200')
  const [saving, setSaving] = useState(false)
  const [history, setHistory] = useState<CreditEntry[]>([])

  useEffect(() => {
    let live = true
    api
      .accountCredits(account.id)
      .then((entries) => live && setHistory(entries))
      .catch((e: Error) => live && onError(e.message))
    return () => {
      live = false
    }
  }, [account.id, onError])

  async function add() {
    const value = Number(amount)
    if (!Number.isInteger(value) || value === 0) {
      onError('Enter a number other than 0.')
      return
    }
    onError(null)
    setSaving(true)
    try {
      onSaved(await api.grantCredits(account.id, value))
      setHistory(await api.accountCredits(account.id))
    } catch (e) {
      onError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <span className={`accounts-credits${credits < 0 ? ' is-short' : ''}`}>
        <span className="accounts-balance">{credits}</span>
        <small>credits</small>
      </span>
      <span className="accounts-add">
        <input
          type="number"
          aria-label={`${account.email} credits to add`}
          step={10}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== 'Enter') return
            if (!saving) void add()
          }}
        />
        <button type="button" className="btn" aria-label={`Add credits to ${account.email}`} disabled={saving} onClick={() => void add()}>
          Add
        </button>
      </span>
      {history.length > 0 && (
        <details className="accounts-history">
          <summary>History · {history.length}</summary>
          <ul className="credit-lines accounts-history-lines" aria-label={`${account.email} recent charges`}>
            {history.map((entry, i) => (
              <CreditLine key={i} entry={entry} grantedBy="you" />
            ))}
          </ul>
        </details>
      )}
    </>
  )
}
