import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import './SpeakButton.css'

type State = 'idle' | 'loading' | 'playing' | 'failed'

/** Sentences already fetched on this page, so a replay starts at once. */
const fetched = new Map<string, string>()

/** Reads `text` aloud in the voice provider's voice; a second press stops it. */
export function SpeakButton({ text }: { text: string }) {
  const [state, setState] = useState<State>('idle')
  const [error, setError] = useState('')
  const audio = useRef<HTMLAudioElement | null>(null)
  useEffect(() => () => audio.current?.pause(), [])

  const press = async () => {
    if (state === 'loading') return
    if (state === 'playing') {
      audio.current?.pause()
      setState('idle')
      return
    }
    setState('loading')
    try {
      let url = fetched.get(text)
      if (!url) {
        url = URL.createObjectURL(await api.speak(text))
        fetched.set(text, url)
      }
      const player = new Audio(url)
      player.onended = () => setState('idle')
      audio.current = player
      await player.play()
      setState('playing')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setState('failed')
    }
  }

  const label = state === 'playing' ? 'Stop reading' : state === 'loading' ? 'Getting the voice…' : 'Read the sentence aloud'
  return (
    <button
      type="button"
      className={`speak is-${state}`}
      aria-label={label}
      title={state === 'failed' ? `Could not read it: ${error}` : label}
      onClick={(e) => {
        e.stopPropagation()
        void press()
      }}
    >
      {state === 'playing' ? (
        <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill="currentColor" stroke="none" />
          <path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.8a6 6 0 0 1 0 8.4" strokeLinecap="round" />
        </svg>
      )}
    </button>
  )
}
