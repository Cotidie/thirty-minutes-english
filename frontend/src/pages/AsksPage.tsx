import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { AskedCard } from '../components/AskCard'
import type { Ask } from '../types'
import './AsksPage.css'

export function AsksPage() {
  const [params] = useSearchParams()
  const sessionId = params.get('session_id')
  const [asks, setAsks] = useState<Ask[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    const id = sessionId === null ? undefined : Number(sessionId)
    api
      .askCards(id)
      .then((rows) => live && setAsks(rows))
      .catch((e: Error) => live && setError(e.message))
    return () => {
      live = false
    }
  }, [sessionId])

  const back = sessionId === null ? '/' : `/s/${sessionId}`

  return (
    <main className="asks">
      <header className="asks-head">
        <Link to={back}>{sessionId === null ? 'All sessions' : 'Back to the session'}</Link>
        <h1>Asks</h1>
      </header>
      {error && <p className="error">Could not load your asks: {error}</p>}
      {!error && asks === null && <p className="empty">Reading them back…</p>}
      {asks?.length === 0 && <p className="empty">Nothing asked yet. Press A during a session.</p>}
      <ol className="ask-cards">
        {asks?.map((ask) => (
          <AskedCard key={ask.id} ask={ask} />
        ))}
      </ol>
    </main>
  )
}
