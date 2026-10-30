import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Account } from '../types'
import './AccountsPanel.css'

/** Who signed up, and who the admin lets create sessions. A change saves at once, apart from Save. */
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

  async function setCanCreate(account: Account, value: boolean) {
    setError(null)
    try {
      const saved = await api.setCanCreate(account.id, value)
      setAccounts((all) => all.map((a) => (a.id === saved.id ? saved : a)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

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
              <time className="accounts-joined" dateTime={account.created_at}>
                Joined {new Date(account.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
              </time>
            </span>
            <label className="accounts-toggle">
              <input
                type="checkbox"
                aria-label={`${account.email} can create sessions`}
                checked={account.is_admin || account.can_create}
                disabled={account.is_admin}
                onChange={(e) => void setCanCreate(account, e.target.checked)}
              />
              Can create sessions
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}
