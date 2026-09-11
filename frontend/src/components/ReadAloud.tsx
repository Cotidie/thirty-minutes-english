import { useEffect, useRef, useState } from 'react'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'
import { connectReadAloud, type ReadAloudConnection } from '../lib/readAloudClient'

interface Props {
  paragraph: string
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

export function ReadAloud({ paragraph, active, onStart, onEnd }: Props) {
  const [state, setState] = useState<LiveState | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const connRef = useRef<ReadAloudConnection | null>(null)

  useEffect(() => () => connRef.current?.dispose(), [])

  const start = async () => {
    onStart()
    setState(initialLiveState)
    try {
      connRef.current = await connectReadAloud({
        paragraph,
        audio: audioRef.current!,
        onEvent: (event) => setState((s) => applyLiveEvent(s ?? initialLiveState, event)),
        onDisconnect: () => setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped before the round ended.')),
      })
    } catch (e) {
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
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
          {(state.reader || state.coach) && (
            <dl className="read-aloud-captions">
              <dt>You</dt>
              <dd>{state.reader}</dd>
              <dt>Coach</dt>
              <dd>{state.coach}</dd>
            </dl>
          )}
        </>
      )}
    </div>
  )
}
