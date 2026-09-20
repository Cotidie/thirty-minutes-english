import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { startAzureAssessor, type Assessor } from '../lib/assessor/azure'
import { Judge, type AzureWord } from '../lib/assessor/judge'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { applyLiveEvent, initialLiveState, liveFailed, type LiveState } from '../lib/liveSession'
import { ReadingText, type Shown } from './ReadingText'

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
  listening: 'Listening. Read the paragraph aloud; click a mark to hear it.',
  closing: 'Wrapping up…',
  closed: 'Round over.',
  failed: 'Could not start.',
}

/** Everything one round holds besides the live state: the coach, the assessor, and its verdicts. */
interface Round {
  coach: LiveConnection
  assessor: Assessor | null
  judge: Judge
  findings: Shown[]
  /** Paragraph positions the reader clicked, so only those get a spoken "Good." */
  asked: Set<number>
}

export function ReadAloud({ paragraph, sessionId, active, onStart, onEnd }: Props) {
  const [state, setState] = useState<LiveState | null>(null)
  const [findings, setFindings] = useState<Shown[]>([])
  const [open, setOpen] = useState<number | null>(null)
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
    setOpen(null)
    try {
      // The assessor is what makes the round worth paying for: no token, no round.
      const session = await api.assessorToken()
      const judge = new Judge({ wordScore: session.word_score, breakConfidence: session.break_confidence }, paragraph)
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
      const round: Round = { coach, assessor: null, judge, findings: [], asked: new Set() }
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

  /** One recognised segment: mark the paragraph, and tell the coach when a word it corrected came out right. */
  const judged = (round: Round, words: AzureWord[]) => {
    const { findings: fresh, confirmed } = round.judge.segment(words)
    if (confirmed.some((c) => round.asked.has(c.at))) round.coach.confirm()
    round.findings = round.findings.map((f) =>
      confirmed.some((c) => c.at === f.at && c.kind === f.kind) ? { ...f, repeated_ok: true } : f,
    )
    round.findings = [...round.findings, ...fresh.map((f) => ({ ...f, repeated_ok: false }))]
    setFindings(round.findings)
  }

  /** The reader clicked a mark: show the card and have the coach say it. */
  const ask = (index: number) => {
    const round = roundRef.current
    if (!round) return
    setOpen(index)
    const f = round.findings[index]
    if (round.asked.has(f.at) || f.repeated_ok) return
    round.asked.add(f.at)
    round.coach.correct(f)
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

  /** The reader is done: the coach goes over what is still open, or signs off when nothing is. */
  const done = () => roundRef.current?.coach.review(roundRef.current.judge.pending())
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
  const card = open === null ? null : findings[open]

  return (
    <div className={`read-aloud${live ? ' is-live' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {state === null ? (
        <button type="button" className="read-aloud-start" onClick={start} disabled={active}>
          Read aloud
        </button>
      ) : (
        <>
          <ReadingText paragraph={paragraph} findings={findings} open={open} onOpen={ask} />
          {card && (
            <p className="reading-card">
              <b>{card.word}</b>
              {card.kind === 'phrasing' ? `paused after "${card.word.split(' ')[0]}": say it as one piece` : `heard ${card.heard}: say ${card.fix}`}
              {card.repeated_ok && <span className="read-aloud-ok">✓</span>}
            </p>
          )}
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
