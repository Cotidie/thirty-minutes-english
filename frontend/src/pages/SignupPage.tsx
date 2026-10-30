import { useState } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { safeNext } from '../lib/safeNext'
import { AuthLayout, Blank, EMAIL_INPUT } from './AuthLayout'

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MIN_PASSWORD = 8
const EMAIL_ASK = 'Enter an email address, like you@example.com.'

export function SignupPage() {
  const { me, loading, signUp } = useAuth()
  const [params] = useSearchParams()
  const { search } = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [tried, setTried] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) return null
  if (me) return <Navigate to={safeNext(params.get('next'))} replace />

  const emailBad = tried && !EMAIL.test(email.trim())
  const shortBad = tried && password.length < MIN_PASSWORD
  const mismatch = (tried || confirm.length > 0) && confirm !== password

  async function submit() {
    setTried(true)
    setError(null)
    if (!EMAIL.test(email.trim()) || password.length < MIN_PASSWORD || confirm !== password) return
    setBusy(true)
    try {
      await signUp(email, password)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      onSubmit={() => void submit()}
      submitLabel="Create account"
      busy={busy}
      sentence={
        <>
          <span className="auth-lead is-opening">Hi, I'm new here.</span> <span className="auth-lead">My email is</span>{' '}
          <Blank {...EMAIL_INPUT} id="email" label="Email" fits="email" enterKeyHint="next" end="," tight={emailBad} bad={emailBad} value={email} onChange={(e) => setEmail(e.target.value)} />{' '}
          {emailBad && <span role="alert" className="auth-note auth-in-sentence is-bad">{EMAIL_ASK}</span>}{' '}
          <span className="auth-lead">I'd like my password to be</span>{' '}
          <Blank id="password" label="Password" fits="password" type="password" autoComplete="new-password" enterKeyHint="next" end="," tight bad={shortBad} value={password} onChange={(e) => setPassword(e.target.value)} />{' '}
          <span className={`auth-note auth-in-sentence${shortBad ? ' is-bad' : ''}`}>At least {MIN_PASSWORD} characters.</span>{' '}
          <span className="auth-lead">and one more time, that's</span>{' '}
          <Blank id="confirm" label="Confirm password" fits="password" type="password" autoComplete="new-password" enterKeyHint="go" end="." last bad={mismatch} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </>
      }
      notes={
        <>
          <p className={`auth-note auth-below${shortBad ? ' is-bad' : ''}`}>Passwords need at least {MIN_PASSWORD} characters.</p>
          {emailBad && <p role="alert" className="auth-note auth-below is-bad">{EMAIL_ASK}</p>}
          {mismatch && <p role="alert" className="auth-note is-bad">The two passwords don't match yet.</p>}
          {error && <p role="alert" className="auth-note is-bad">{error}</p>}
        </>
      }
      other={
        <>
          Already have an account? <Link to={`/login${search}`}>Sign in</Link>
        </>
      }
    />
  )
}
