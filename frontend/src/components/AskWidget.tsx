import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useMatch } from 'react-router-dom'
import { api } from '../api'
import { connectAsk, type LiveConnection } from '../lib/liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'

/** How long the coach stays quiet before we take the round as finished. */
const SILENCE_MS = 5000

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Ask away. "How do you say…"',
  closing: 'Saving…',
  closed: 'Saved.',
  failed: 'Could not start.',
}

export function AskWidget() {
  const match = useMatch('/s/:id')
  const sessionId = match?.params.id ? Number(match.params.id) : null
  const [state, setState] = useState<LiveState | null>(null)
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

  const save = useCallback(
    async (round: LiveState) => {
      const user_text = round.user.trim()
      const coach_text = round.coach.trim()
      if (!user_text || !coach_text) return
      await api
        .addAsk({ session_id: sessionId, user_text, coach_text, seconds: round.seconds })
        .catch(() => undefined)
    },
    [sessionId],
  )

  const close = useCallback(() => {
    clearSilence()
    setState((s) => (s ? { ...s, status: 'closing' } : s))
    connRef.current?.close()
    const round = latest.current
    if (round) void save(round)
  }, [save])

  const start = useCallback(async () => {
    setState(initialLiveState)
    try {
      const topic = sessionId === null ? null : await api.getSession(sessionId).then((s) => s.content.topic, () => null)
      connRef.current = await connectAsk(topic, {
        audio: audioRef.current!,
        onEvent: (event) => {
          setState((s) => applyLiveEvent(s ?? initialLiveState, event))
          if (event.type === 'session.output_transcript.delta') {
            clearSilence()
            silence.current = setTimeout(close, SILENCE_MS)
          }
        },
        onDisconnect: () => setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped.')),
      })
    } catch (e) {
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
  }, [close, sessionId])

  const dismiss = useCallback(() => {
    clearSilence()
    connRef.current?.dispose()
    connRef.current = null
    setState(null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        if (latest.current?.status === 'listening') close()
        else dismiss()
        return
      }
      if (e.key !== 'a' || open || e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return
      e.preventDefault()
      void start()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, dismiss, open, start])

  return (
    <div className={`ask${open ? ' is-open' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {state === null ? (
        <div className="ask-idle">
          <button type="button" className="ask-start" onClick={() => void start()}>
            🎤 Ask <kbd>a</kbd>
          </button>
          <Link className="ask-review" to={sessionId === null ? '/asks' : `/asks?session_id=${sessionId}`}>
            Asks
          </Link>
        </div>
      ) : (
        <div className="ask-panel" role="dialog" aria-label="Ask the coach">
          <div className="ask-bar">
            <span className="ask-status" role="status">
              {STATUS_LABEL[state.status]}
            </span>
            {state.seconds > 0 && <span className="ask-seconds">{state.seconds}s</span>}
            {state.status === 'listening' && (
              <button type="button" onClick={close}>
                Done
              </button>
            )}
            {(state.status === 'closed' || state.status === 'failed') && (
              <button type="button" onClick={dismiss}>
                Close
              </button>
            )}
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
        </div>
      )}
    </div>
  )
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
