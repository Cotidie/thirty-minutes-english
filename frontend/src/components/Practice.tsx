import { useRef } from 'react'
import { api } from '../api'
import { connectExample } from '../lib/liveClient'
import type { LiveState } from '../lib/liveSession'
import { useMicLevel } from '../lib/micLevel'
import { hasBothLines, useLiveRound } from '../lib/useLiveRound'
import type { Example, PracticeTarget } from '../types'
import { MicMeter } from './MicMeter'

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Say one sentence with it',
  closing: 'Wrapping up…',
  closed: 'Round over',
  failed: 'Could not start',
}

interface Props {
  target: PracticeTarget
  label: string
  sessionId: number
  /** Sentences already made with this target, oldest first. */
  examples: Example[]
  onKept: (example: Example) => void
}

/**
 * A button under an expression or word. One press is one sentence: the coach
 * says it back the native way and adds a line of feedback; Keep stacks it
 * under the target.
 */
export function Practice({ target, label, sessionId, examples, onKept }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const round = useLiveRound(
    audioRef,
    (opts) => connectExample(target, opts),
    async (r) => {
      onKept(
        await api.addExample({
          session_id: sessionId,
          expression: target.text,
          user_text: r.user.trim(),
          coach_text: r.coach.trim(),
          seconds: r.seconds,
        }),
      )
    },
  )
  const { state, start, close, dismiss, save } = round
  const level = useMicLevel(round.microphone)

  const keep = async () => {
    if (await save()) dismiss()
  }

  return (
    <div className="practice">
      <audio ref={audioRef} autoPlay />
      {examples.length > 0 && (
        <ol className="sentences" aria-label={`Sentences with ${target.text}`}>
          {examples.map((ex) => (
            <li key={ex.id} className="sentence">
              <p className="sentence-said">{ex.user_text}</p>
              <p className="sentence-echo">{ex.coach_text}</p>
            </li>
          ))}
        </ol>
      )}
      {state === null ? (
        <button type="button" className="practice-start" onClick={() => void start()}>
          {label}
        </button>
      ) : (
        <div className="ask-slip practice-slip" role="dialog" aria-label={`Practice ${target.text}`}>
          <div className="ask-bar">
            {state.status === 'listening' && <MicMeter level={level} />}
            <span className="ask-status" role="status">
              {STATUS_LABEL[state.status]}
            </span>
            {state.seconds > 0 && <span className="ask-seconds">{state.seconds}s</span>}
            <button type="button" className="slip-icon" aria-label="Retry" title="Retry" onClick={() => void start()}>
              ↻
            </button>
            <button type="button" className="slip-icon" aria-label="Discard" title="Discard" onClick={dismiss}>
              ✕
            </button>
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
            <span className="ask-hint">{hintFor(state)}</span>
            {state.status === 'listening' && (
              <button type="button" onClick={close}>
                Done
              </button>
            )}
            {state.status === 'closed' && (
              <button type="button" className="ask-save" onClick={() => void keep()} disabled={!hasBothLines(state)}>
                Keep
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function hintFor(state: LiveState): string {
  if (state.status === 'listening') return 'Misheard? ↻ starts over'
  if (state.status === 'closed') return hasBothLines(state) ? 'Keep it, or ✕ to drop it' : 'Nothing came through'
  return ''
}
