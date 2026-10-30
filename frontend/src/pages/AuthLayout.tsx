import type { FormEvent, InputHTMLAttributes, ReactNode } from 'react'
import './AuthPage.css'

interface LayoutProps {
  onSubmit: () => void
  /** The form's one sentence, its blanks among the words. */
  sentence: ReactNode
  /** What goes between the sentence and the button: hints and errors. */
  notes: ReactNode
  submitLabel: string
  busy: boolean
  /** The way to the other page. */
  other: ReactNode
}

/** The login and signup pages: a form that reads as one English sentence with blanks to fill. */
export function AuthLayout({ onSubmit, sentence, notes, submitLabel, busy, other }: LayoutProps) {
  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <main className="auth">
      <header className="auth-top">
        <h1 className="auth-brand">Thirty minutes of English</h1>
        <div aria-hidden="true" className="auth-bar" />
        <p className="auth-lede">
          A few expressions, one short article, and the words around it. Everything you two need to talk for half an hour.
        </p>
      </header>
      <form noValidate onSubmit={submit} className="auth-ask">
        <div className="auth-say">{sentence}</div>
        {notes}
        <div className="auth-acts">
          <button type="submit" className="auth-go" disabled={busy}>
            {submitLabel}
          </button>
          <p className="auth-switch">{other}</p>
        </div>
      </form>
    </main>
  )
}

interface BlankProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string
  label: string
  fits: 'email' | 'password'
  /** The punctuation that closes this part of the sentence. */
  end?: string
  bad?: boolean
  /** A hint follows right under the blank on a phone. */
  tight?: boolean
  last?: boolean
}

/** A blank in the sentence. Its label is for screen readers: the sentence around it is what the eye reads. */
export function Blank({ id, label, fits, end, bad, tight, last, ...input }: BlankProps) {
  return (
    <span className={`auth-slot${tight ? ' is-tight' : ''}${last ? ' is-last' : ''}`}>
      <label htmlFor={id} className="auth-sr">
        {label}
      </label>
      <input id={id} name={id} className={`auth-blank auth-blank-${fits}${bad ? ' is-bad' : ''}`} {...input} />
      {end && <span className="auth-end">{end}</span>}
    </span>
  )
}

/** What makes the email blank easy to fill on a phone. */
export const EMAIL_INPUT = {
  type: 'email',
  inputMode: 'email',
  autoCapitalize: 'none',
  spellCheck: false,
  autoComplete: 'username',
  placeholder: 'you@example.com',
} as const
