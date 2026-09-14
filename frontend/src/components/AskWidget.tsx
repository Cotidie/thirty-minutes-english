import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useMatch } from 'react-router-dom'
import { api } from '../api'
import { connectAsk, type LiveConnection } from '../lib/liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'
import { LEVEL_STEPS, useMicLevel } from '../lib/micLevel'

/** How long the coach stays quiet before we take the round as finished. */
const SILENCE_MS = 5000

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Listening',
  closing: 'Wrapping up…',
  closed: 'Round over',
  failed: 'Could not start',
}

export function AskWidget() {
  const match = useMatch('/s/:id')
  const sessionId = match?.params.id ? Number(match.params.id) : null
  const [state, setState] = useState<LiveState | null>(null)
  const [saved, setSaved] = useState(false)
  const [microphone, setMicrophone] = useState<MediaStream | null>(null)
  const level = useMicLevel(microphone)
  const audioRef = useRef<HTMLAudioElement>(null)
  const connRef = useRef<LiveConnection | null>(null)
  const latest = useRef<LiveState | null>(null)
  const silence = useRef<ReturnType<typeof setTimeout> | null>(null)

  const open = state !== null

  // The silence timer and the key handler both need the round as it stands now.
  useEffect(() => {
    latest.current = state
  }, [state])

  const clearSilence = () => {
    if (silence.current) clearTimeout(silence.current)
    silence.current = null
  }

  useEffect(() => () => {
    clearSilence()
    connRef.current?.dispose()
  }, [])

  /** Only what the user chose to keep: a misheard or useless round is thrown away. */
  const save = useCallback(async () => {
    const round = latest.current
    if (!round) return
    setSaved(true)
    try {
      await api.addAsk({
        session_id: sessionId,
        user_text: round.user.trim(),
        coach_text: round.coach.trim(),
        seconds: round.seconds,
      })
    } catch (e) {
      setSaved(false)
      setState((s) => (s ? { ...s, error: e instanceof Error ? e.message : String(e) } : s))
    }
  }, [sessionId])

  const close = useCallback(() => {
    clearSilence()
    setMicrophone(null)
    setState((s) => (s ? { ...s, status: 'closing' } : s))
    connRef.current?.close()
  }, [])

  /** Also the retry: drops whatever was said and opens a fresh round. */
  const start = useCallback(async () => {
    clearSilence()
    connRef.current?.dispose()
    connRef.current = null
    setMicrophone(null)
    setState(initialLiveState)
    setSaved(false)
    try {
      const topic = sessionId === null ? null : await api.getSession(sessionId).then((s) => s.content.topic, () => null)
      const conn = await connectAsk(topic, {
        audio: audioRef.current!,
        onEvent: (event) => {
          setState((s) => applyLiveEvent(s ?? initialLiveState, event))
          if (event.type === 'session.output_transcript.delta') {
            clearSilence()
            silence.current = setTimeout(close, SILENCE_MS)
          }
        },
        onDisconnect: () => {
          setMicrophone(null)
          setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped.'))
        },
      })
      connRef.current = conn
      setMicrophone(conn.microphone)
    } catch (e) {
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
  }, [close, sessionId])

  const dismiss = useCallback(() => {
    clearSilence()
    connRef.current?.dispose()
    connRef.current = null
    setMicrophone(null)
    setState(null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      const round = latest.current
      if (!open) {
        if (e.key !== 'a') return
        e.preventDefault()
        void start()
        return
      }
      if (e.key === 'Escape') {
        if (round?.status === 'listening') close()
        else dismiss()
      } else if (e.key === 'r') {
        e.preventDefault()
        void start()
      } else if (e.key === 'Enter' && round?.status === 'closed' && !saved && worthSaving(round)) {
        e.preventDefault()
        void save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, dismiss, open, save, saved, start])

  return (
    <div className={`ask${open ? ' is-open' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {state === null ? (
        <div className="ask-rule">
          <button type="button" className="ask-start" onClick={() => void start()}>
            Ask <kbd>a</kbd>
          </button>
          <Link className="ask-review" to={sessionId === null ? '/asks' : `/asks?session_id=${sessionId}`}>
            Asks
          </Link>
        </div>
      ) : (
        <div className="ask-slip" role="dialog" aria-label="Ask the coach">
          <div className="ask-bar">
            {state.status === 'listening' && <MicMeter level={level} />}
            <span className="ask-status" role="status">
              {saved ? 'Saved' : STATUS_LABEL[state.status]}
            </span>
            {state.seconds > 0 && <span className="ask-seconds">{state.seconds}s</span>}
          </div>

          {state.error && <p className="ask-error">{state.error}</p>}

          {(state.user || state.coach) && (
            <dl className="ask-captions">
              <dt>You</dt>
              <dd>{state.user}</dd>
              <dt>Coach</dt>
              <dd>{state.coach}</dd>
            </dl>
          )}

          <div className="ask-actions">
            <span className="ask-hint">{hintFor(state, saved)}</span>
            <button type="button" onClick={() => void start()}>
              Retry <kbd>r</kbd>
            </button>
            {state.status === 'listening' ? (
              <button type="button" onClick={close}>
                Done
              </button>
            ) : (
              <button type="button" onClick={dismiss}>
                {saved ? 'Close' : 'Discard'}
              </button>
            )}
            {state.status === 'closed' && !saved && (
              <button type="button" className="ask-save" onClick={() => void save()} disabled={!worthSaving(state)}>
                Save
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Five bars that fill with how loud the microphone is, so silence is visible. */
function MicMeter({ level }: { level: number }) {
  return (
    <span className={`ask-level${level === 0 ? ' is-quiet' : ''}`} aria-hidden="true">
      {Array.from({ length: LEVEL_STEPS }, (_, i) => (
        <i key={i} className={i < level ? 'is-on' : ''} />
      ))}
    </span>
  )
}

function hintFor(state: LiveState, saved: boolean): string {
  if (saved) return 'Kept for review'
  if (state.status === 'listening') return 'Missed your moment? Retry'
  if (state.status === 'closed') return worthSaving(state) ? 'Enter to save, Esc to discard' : 'Nothing came through'
  return ''
}

/** A round with nothing on one of the two lines has nothing to review later. */
function worthSaving(state: LiveState): boolean {
  return state.user.trim() !== '' && state.coach.trim() !== ''
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
