import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { startAzureAssessor, type Assessor } from '../lib/assessor/azure'
import { Judge, type AzureWord } from '../lib/assessor/judge'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { spoken } from '../lib/liveSession'
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

type Phase = 'connecting' | 'listening' | 'done' | 'failed'

const STATUS_LABEL: Record<Phase, string> = {
  connecting: 'Connecting…',
  listening: 'Listening. Read the paragraph aloud; click a mark to hear it.',
  done: 'Round over. The marks stay: click one to hear it.',
  failed: 'Could not start.',
}

/** The coach stays on this long after its last word, then hangs up. */
export const COACH_SILENCE_MS = 2000
/** No word at all from the coach by then: hang up anyway. */
const COACH_TIMEOUT_MS = 15_000

/** The reading: the microphone, Azure on it, and the judge's verdicts on the paragraph. */
interface Round {
  microphone: MediaStream
  assessor: Assessor | null
  judge: Judge
  findings: Shown[]
  heard: string
  startedAt: number
}

/** One coach call for one clicked mark: opened, spoken, hung up. */
interface Call {
  coach: LiveConnection
  timer: ReturnType<typeof setTimeout> | null
}

/**
 * Read aloud with the assessor as the only listener. Azure marks the paragraph
 * as the reader goes; the coach is dialled only when a mark is clicked, says
 * its two beats, and hangs up.
 */
export function ReadAloud({ paragraph, sessionId, active, onStart, onEnd }: Props) {
  const [phase, setPhase] = useState<Phase | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [heard, setHeard] = useState('')
  const [seconds, setSeconds] = useState(0)
  const [findings, setFindings] = useState<Shown[]>([])
  const [open, setOpen] = useState<number | null>(null)
  const [said, setSaid] = useState('')
  const audioRef = useRef<HTMLAudioElement>(null)
  const roundRef = useRef<Round | null>(null)
  const callRef = useRef<Call | null>(null)

  useEffect(
    () => () => {
      hangUp()
      void endRound()
    },
    [],
  )

  const start = async () => {
    onStart()
    setPhase('connecting')
    setError(null)
    setHeard('')
    setSeconds(0)
    setFindings([])
    setOpen(null)
    setSaid('')
    try {
      const session = await api.assessorToken()
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
      const round: Round = {
        microphone,
        assessor: null,
        judge: new Judge({ wordScore: session.word_score, breakConfidence: session.break_confidence }, paragraph),
        findings: [],
        heard: '',
        startedAt: Date.now(),
      }
      roundRef.current = round
      round.assessor = await startAzureAssessor({
        microphone,
        paragraph,
        session,
        onSegment: (words, text) => judged(round, words, text),
        onError: (message) => setError(`Assessor: ${message}`),
      })
      setPhase('listening')
    } catch (e) {
      void endRound()
      setError(e instanceof Error ? e.message : String(e))
      setPhase('failed')
    }
  }

  /** One recognised segment: extend the transcript and mark the paragraph. */
  const judged = (round: Round, words: AzureWord[], text: string) => {
    const { findings: fresh, confirmed } = round.judge.segment(words)
    round.findings = [
      ...round.findings.map((f) => (confirmed.some((c) => c.at === f.at && c.kind === f.kind) ? { ...f, repeated_ok: true } : f)),
      ...fresh.map((f) => ({ ...f, repeated_ok: false })),
    ]
    setFindings(round.findings)
    if (text) {
      round.heard = round.heard ? `${round.heard} ${text}` : text
      setHeard(round.heard)
    }
  }

  /** Releases the microphone and Azure. Safe to call twice. */
  const endRound = async () => {
    const round = roundRef.current
    if (!round) return
    round.microphone.getTracks().forEach((t) => t.stop())
    const { assessor } = round
    round.assessor = null
    await assessor?.stop()
  }

  /** The reader clicked a mark: show its card and have the coach say it. */
  const ask = (index: number) => {
    setOpen(index)
    const f = roundRef.current?.findings[index]
    if (f) void speak(f)
  }

  const speak = async (finding: Shown) => {
    hangUp()
    setSaid('')
    let text = ''
    try {
      const coach = await connectReadAloud(paragraph, {
        audio: audioRef.current!,
        onEvent: (event) => {
          if (event.type === 'session.started') coach.correct(finding)
          if (event.type === 'session.output_transcript.delta') {
            text = spoken(text + (event.delta ?? ''))
            setSaid(text)
            linger(COACH_SILENCE_MS)
          }
          if (event.type === 'session.closed') hangUp()
        },
        onDisconnect: hangUp,
      })
      // The coach only speaks here; what the reader says next is Azure's to judge.
      coach.microphone.getAudioTracks().forEach((t) => (t.enabled = false))
      callRef.current = { coach, timer: null }
      linger(COACH_TIMEOUT_MS)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  /** Hang up once the coach has been quiet this long. */
  const linger = (ms: number) => {
    const call = callRef.current
    if (!call) return
    if (call.timer) clearTimeout(call.timer)
    call.timer = setTimeout(() => call.coach.close(), ms)
  }

  const hangUp = () => {
    const call = callRef.current
    if (!call) return
    callRef.current = null
    if (call.timer) clearTimeout(call.timer)
    call.coach.dispose()
  }

  /** The reader is done: the round is filed; the marks stay clickable. */
  const done = async () => {
    const round = roundRef.current
    if (!round) return
    const elapsed = Math.round((Date.now() - round.startedAt) / 1000)
    setSeconds(elapsed)
    setPhase('done')
    await endRound()
    if (round.findings.length === 0) return
    await api
      .addReading({
        session_id: sessionId,
        paragraph,
        user_text: round.heard,
        coach_text: '',
        seconds: elapsed,
        corrections: round.findings.map(({ kind, word, heard, fix, repeated_ok }) => ({ kind, word, heard, fix, repeated_ok })),
      })
      .catch(() => undefined)
  }

  const reset = () => {
    hangUp()
    void endRound()
    roundRef.current = null
    setPhase(null)
    onEnd()
  }

  const card = open === null ? null : findings[open]

  return (
    <div className={`read-aloud${phase === 'listening' ? ' is-live' : ''}`}>
      <audio ref={audioRef} autoPlay />
      {phase === null ? (
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
              {said && <span className="reading-said">{said}</span>}
            </p>
          )}
          <div className="read-aloud-bar">
            <span className="read-aloud-status" role="status">
              {STATUS_LABEL[phase]}
            </span>
            {seconds > 0 && <span className="read-aloud-seconds">{seconds}s</span>}
            {phase === 'listening' && (
              <button type="button" onClick={() => void done()}>
                Done
              </button>
            )}
            {(phase === 'done' || phase === 'failed') && (
              <button type="button" onClick={reset}>
                Close
              </button>
            )}
          </div>
          {error && <p className="read-aloud-error">{error}</p>}
          {heard && (
            <dl className="read-aloud-captions">
              <dt>You</dt>
              <dd>{heard}</dd>
            </dl>
          )}
        </>
      )}
    </div>
  )
}
