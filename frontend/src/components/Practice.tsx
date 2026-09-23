import { useRef, useState } from 'react'
import { api } from '../api'
import { connectExample } from '../lib/liveClient'
import type { LiveState } from '../lib/liveSession'
import { useMicLevel } from '../lib/micLevel'
import { useLiveRound } from '../lib/useLiveRound'
import type { Example, ExampleFeedback, PracticeTarget } from '../types'
import { Slip } from './Slip'
import './Practice.css'

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
 * A button under an expression or word. One press is one sentence: the live
 * coach hears it, a text model writes it back the native way with a line per
 * change, the live coach reads that aloud; Keep stacks it under the target.
 */
export function Practice({ target, label, sessionId, examples, onKept }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [answer, setAnswer] = useState<ExampleFeedback | null>(null)
  const [writing, setWriting] = useState(false)
  const round = useLiveRound(
    audioRef,
    (opts) => connectExample(target, opts),
    async (r) => {
      onKept(
        await api.addExample({
          session_id: sessionId,
          expression: target.text,
          user_text: r.user.trim(),
          coach_text: spoken(answer!),
          seconds: r.seconds,
        }),
      )
    },
    async (r, say) => {
      setWriting(true)
      try {
        const written = await api.exampleFeedback(target, r.user.trim())
        setAnswer(written)
        say(spoken(written))
      } finally {
        setWriting(false)
      }
    },
  )
  const { state, close, dismiss, save } = round
  const level = useMicLevel(round.microphone)

  const start = () => {
    setAnswer(null)
    setWriting(false)
    return round.start()
  }

  const keep = async () => {
    if (await save()) dismiss()
  }
  const complete = answer !== null && state !== null && state.user.trim() !== ''

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
        <Slip
          label={`Practice ${target.text}`}
          className="practice-slip"
          state={state}
          level={level}
          status={STATUS_LABEL[state.status]}
          tools={
            <>
              <button type="button" className="slip-icon" aria-label="Retry" title="Retry" onClick={() => void start()}>
                ↻
              </button>
              <button type="button" className="slip-icon" aria-label="Discard" title="Discard" onClick={dismiss}>
                ✕
              </button>
            </>
          }
          hint={hintFor(state, writing, complete)}
          actions={
            <>
              {state.status === 'listening' && (
                <button type="button" onClick={close}>
                  Done
                </button>
              )}
              {state.status === 'closed' && (
                <button type="button" className="ask-save" onClick={() => void keep()} disabled={!complete}>
                  Keep
                </button>
              )}
            </>
          }
        >
          {(state.user || answer) && (
            <dl className="ask-captions">
              <dt>You</dt>
              <dd>{state.user}</dd>
              {answer && (
                <>
                  <dt>Coach</dt>
                  <dd className="practice-answer">
                    <span>{answer.paraphrase}</span>
                    <ul className="practice-notes" aria-label="Feedback">
                      {answer.feedback.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </dd>
                </>
              )}
            </dl>
          )}
        </Slip>
      )}
    </div>
  )
}

/** The answer as one line: what the coach reads aloud and what gets saved. */
function spoken(answer: ExampleFeedback): string {
  return [answer.paraphrase, ...answer.feedback].join(' ')
}

function hintFor(state: LiveState, writing: boolean, complete: boolean): string {
  if (writing) return 'Writing the native version…'
  if (state.status === 'listening') return 'Misheard? ↻ starts over'
  if (state.status === 'closed') return complete ? 'Keep it, or ✕ to drop it' : 'Nothing came through'
  return ''
}
