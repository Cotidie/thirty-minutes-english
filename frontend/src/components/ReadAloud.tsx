import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'

interface Props {
  paragraph: string
  /** Where a finished round is filed, when the reading happens inside a session. */
  sessionId: number | null
  /** Only one paragraph may hold the microphone at a time. */
  active: boolean
  onStart: () => void
  onEnd: () => void
}

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Listening. Read the paragraph aloud.',
  closing: 'Wrapping up…',
  closed: 'Round over.',
  failed: 'Could not start.',
}

export function ReadAloud({ paragraph, sessionId, active, onStart, onEnd }: Props) {
  const [state, setState] = useState<LiveState | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const connRef = useRef<LiveConnection | null>(null)

  useEffect(() => () => connRef.current?.dispose(), [])

  const start = async () => {
    onStart()
    setState(initialLiveState)
    try {
      connRef.current = await connectReadAloud(paragraph, {
        audio: audioRef.current!,
        onEvent: (event) => {
          setState((s) => {
            const next = applyLiveEvent(s ?? initialLiveState, event)
            if (event.type === 'session.closed') void keep(next)
            return next
          })
        },
        onDisconnect: () => setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped before the round ended.')),
      })
    } catch (e) {
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
  }

  /** A round the coach spoke in is worth keeping; a silent one has no findings. */
  const keep = async (round: LiveState) => {
    if (!round.coach.trim()) return
    await api
      .addReading({
        session_id: sessionId,
        paragraph,
        user_text: round.user.trim(),
        coach_text: round.coach.trim(),
        seconds: round.seconds,
      })
      .catch(() => undefined)
  }

  const finish = () => connRef.current?.finish()
  const stop = () => {
    setState((s) => (s ? { ...s, status: 'closing' } : s))
    connRef.current?.close()
  }
  const reset = () => {
    connRef.current = null
    setState(null)
    onEnd()
  }

  const live = state !== null && state.status !== 'closed' && state.status !== 'failed'

  return (
    <div className={`read-aloud${live ? ' is-live' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {state === null ? (
        <button type="button" className="read-aloud-start" onClick={start} disabled={active}>
          Read aloud
        </button>
      ) : (
        <>
          <div className="read-aloud-bar">
            <span className="read-aloud-status" role="status">
              {STATUS_LABEL[state.status]}
            </span>
            {state.seconds > 0 && <span className="read-aloud-seconds">{state.seconds}s</span>}
            {state.status === 'listening' && (
              <>
                <button type="button" onClick={finish}>Finish</button>
                <button type="button" onClick={stop}>Stop</button>
              </>
            )}
            {(state.status === 'closed' || state.status === 'failed') && (
              <button type="button" onClick={reset}>Done</button>
            )}
          </div>
          {state.error && <p className="read-aloud-error">{state.error}</p>}
          {(state.user || state.coach) && (
            <dl className="read-aloud-captions">
              <dt>You</dt>
              <dd>{state.user}</dd>
              <dt>Coach</dt>
              <dd>{state.coach}</dd>
            </dl>
          )}
        </>
      )}
    </div>
  )
}
