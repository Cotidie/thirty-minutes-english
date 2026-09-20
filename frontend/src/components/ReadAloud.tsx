import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { startAzureAssessor, type Assessor } from '../lib/assessor/azure'
import { Judge, type AzureWord, type Finding } from '../lib/assessor/judge'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'
import type { AssessorSession } from '../types'

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

/** A finding as it is filed: the assessor's verdict plus whether the repeat came out right. */
interface Filed extends Finding {
  repeated_ok: boolean
}

/** Everything one round holds besides the live state: the coach, the assessor, and its verdicts. */
interface Round {
  coach: LiveConnection
  assessor: Assessor | null
  judge: Judge
  mode: AssessorSession['feedback']
  findings: Filed[]
}

export function ReadAloud({ paragraph, sessionId, active, onStart, onEnd }: Props) {
  const [state, setState] = useState<LiveState | null>(null)
  const [findings, setFindings] = useState<Filed[]>([])
  const audioRef = useRef<HTMLAudioElement>(null)
  const roundRef = useRef<Round | null>(null)

  useEffect(
    () => () => {
      roundRef.current?.coach.dispose()
      void roundRef.current?.assessor?.stop()
    },
    [],
  )

  const start = async () => {
    onStart()
    setState(initialLiveState)
    setFindings([])
    try {
      // The assessor is what makes the round worth paying for: no token, no round.
      const session = await api.assessorToken()
      const judge = new Judge({ wordScore: session.word_score, breakConfidence: session.break_confidence }, session.feedback)
      const coach = await connectReadAloud(paragraph, {
        audio: audioRef.current!,
        onEvent: (event) => {
          setState((s) => {
            const next = applyLiveEvent(s ?? initialLiveState, event)
            if (event.type === 'session.closed') {
              void roundRef.current?.assessor?.stop()
              void keep(next)
            }
            return next
          })
        },
        onDisconnect: () => {
          void roundRef.current?.assessor?.stop()
          setState((s) => liveFailed(s ?? initialLiveState, 'Connection dropped before the round ended.'))
        },
      })
      const round: Round = { coach, assessor: null, judge, mode: session.feedback, findings: [] }
      roundRef.current = round
      round.assessor = await startAzureAssessor({
        microphone: coach.microphone,
        paragraph,
        session,
        onSegment: (words) => judged(round, words),
        onError: (message) => setState((s) => ({ ...(s ?? initialLiveState), error: `Assessor: ${message}` })),
      })
    } catch (e) {
      roundRef.current?.coach.dispose()
      setState((s) => liveFailed(s ?? initialLiveState, e instanceof Error ? e.message : String(e)))
    }
  }

  /** One recognised segment: file what the judge found, and tell the coach when it is its turn. */
  const judged = (round: Round, words: AzureWord[]) => {
    const { findings: fresh, confirmed } = round.judge.segment(words)
    if (confirmed.length > 0) {
      round.coach.confirm()
      round.findings = round.findings.map((f) =>
        confirmed.some((c) => c.word === f.word) && !f.repeated_ok ? { ...f, repeated_ok: true } : f,
      )
    }
    if (fresh.length > 0) {
      if (round.mode === 'interrupt') round.coach.correct(fresh[0])
      round.findings = [...round.findings, ...fresh.map((f) => ({ ...f, repeated_ok: false }))]
    }
    setFindings(round.findings)
  }

  /** A round with findings or coach speech is worth keeping; a silent clean one has nothing to file. */
  const keep = async (live: LiveState) => {
    const corrections = (roundRef.current?.findings ?? []).map(({ kind, word, heard, fix, repeated_ok }) => ({
      kind,
      word,
      heard,
      fix,
      repeated_ok,
    }))
    if (!live.coach.trim() && corrections.length === 0) return
    await api
      .addReading({
        session_id: sessionId,
        paragraph,
        user_text: live.user.trim(),
        coach_text: live.coach.trim() || 'Goodbye.',
        seconds: live.seconds,
        corrections,
      })
      .catch(() => undefined)
  }

  /** The reader is done: the coach signs off, or in after mode reviews what is open first. */
  const done = () => {
    const round = roundRef.current
    if (!round) return
    if (round.mode === 'after') round.coach.review(round.judge.finish())
    else round.coach.finish()
  }
  const stop = () => {
    setState((s) => (s ? { ...s, status: 'closing' } : s))
    roundRef.current?.coach.close()
  }
  const reset = () => {
    roundRef.current = null
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
                <button type="button" onClick={done}>Done</button>
                <button type="button" onClick={stop}>Stop</button>
              </>
            )}
            {(state.status === 'closed' || state.status === 'failed') && (
              <button type="button" onClick={reset}>Close</button>
            )}
          </div>
          {state.error && <p className="read-aloud-error">{state.error}</p>}
          {findings.length > 0 && (
            <ul className="read-aloud-findings" aria-label="Findings">
              {findings.map((f, i) => (
                <li key={`${f.word}-${i}`} className={`is-${f.kind}${f.repeated_ok ? ' is-ok' : ''}`}>
                  <b>{f.word}</b> {f.heard}
                  {f.repeated_ok && <span className="read-aloud-ok">✓</span>}
                </li>
              ))}
            </ul>
          )}
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
