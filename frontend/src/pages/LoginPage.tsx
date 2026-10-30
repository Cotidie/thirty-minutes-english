import { useState } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { safeNext } from '../lib/safeNext'
import { AuthLayout, Blank, EMAIL_INPUT } from './AuthLayout'

export function LoginPage() {
  const { me, loading, logIn } = useAuth()
  const [params] = useSearchParams()
  const { search } = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) return null
  if (me) return <Navigate to={safeNext(params.get('next'))} replace />

  async function submit() {
    if (!email.trim() || !password) return setError('Enter your email and password.')
    setError(null)
    setBusy(true)
    try {
      await logIn(email, password)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      onSubmit={() => void submit()}
      submitLabel="Sign in"
      busy={busy}
      sentence={
        <>
          <span className="auth-lead">Hi, my email is</span>{' '}
          <Blank {...EMAIL_INPUT} id="email" label="Email" fits="email" enterKeyHint="next" value={email} onChange={(e) => setEmail(e.target.value)} />{' '}
          <span className="auth-lead">and my password is</span>{' '}
          <Blank id="password" label="Password" fits="password" type="password" autoComplete="current-password" enterKeyHint="go" end="." last value={password} onChange={(e) => setPassword(e.target.value)} />
        </>
      }
      notes={error && <p role="alert" className="auth-note is-bad">{error}</p>}
      other={
        <>
          New here? <Link to={`/signup${search}`}>Create an account</Link>
        </>
      }
    />
  )
}
