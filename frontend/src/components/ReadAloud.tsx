import { useEffect, useRef, useState, type RefObject } from 'react'
import { api } from '../api'
import { startAzureAssessor, type Assessor } from '../lib/assessor/azure'
import { Judge, type AzureWord, type Shown } from '../lib/assessor/judge'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { FindingCard } from './FindingCard'
import './ReadAloud.css'

interface Options {
  paragraph: string
  /** The session a finished round is filed under. */
  sessionId: number
  /** The marks the paragraph's last round left, shown until a new round starts. */
  saved: Shown[]
  onStart: () => void
  /** The microphone is free. */
  onEnd: () => void
}

type Phase = 'connecting' | 'listening' | 'done' | 'failed'

/** A paragraph's read-aloud round as the page sees it. */
export interface ReadAloudRound {
  phase: Phase | null
  error: string | null
  heard: string
  seconds: number
  findings: Shown[]
  /** Index into `findings` of the one whose card is open. */
  open: number | null
  audioRef: RefObject<HTMLAudioElement | null>
  start: () => void
  done: () => void
  /** Close: the marks stay for clicking. */
  reset: () => void
  /** The reader clicked a mark: show its card and have the coach say it. */
  ask: (index: number) => void
}

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
 * as the reader goes; a clicked mark opens the full account in text, and the
 * coach is dialled to say its two beats and hang up.
 */
export function useReadAloud({ paragraph, sessionId, saved, onStart, onEnd }: Options): ReadAloudRound {
  const [phase, setPhase] = useState<Phase | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [heard, setHeard] = useState('')
  const [seconds, setSeconds] = useState(0)
  /** The marks of a round started on this page; until then, the saved ones show. */
  const [fresh, setFresh] = useState<Shown[] | null>(null)
  const findings = fresh ?? saved
  const [open, setOpen] = useState<number | null>(null)
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
    setFresh([])
    setOpen(null)
    try {
      const session = await api.assessorToken()
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
      const round: Round = {
        microphone,
        assessor: null,
        judge: new Judge(session.word_score, paragraph),
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
      ...round.findings.map((f) => (confirmed.some((c) => c.at === f.at) ? { ...f, repeated_ok: true } : f)),
      ...fresh.map((f) => ({ ...f, repeated_ok: false })),
    ]
    setFresh(round.findings)
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
    void speak(findings[index])
  }

  const speak = async (finding: Shown) => {
    hangUp()
    // Gemini reports session.started while connecting, before `coach` exists.
    let coach: LiveConnection | null = null
    let started = false
    try {
      coach = await connectReadAloud(paragraph, {
        audio: audioRef.current!,
        onEvent: (event) => {
          if (event.type === 'session.started') {
            started = true
            coach?.correct(finding)
          }
          if (event.type === 'session.output_transcript.delta') linger(COACH_SILENCE_MS)
          if (event.type === 'session.closed') hangUp()
        },
        onDisconnect: hangUp,
      })
      // The coach only speaks here; what the reader says next is Azure's to judge.
      coach.microphone.getAudioTracks().forEach((t) => (t.enabled = false))
      callRef.current = { coach, timer: null }
      if (started) coach.correct(finding)
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
    // Filed even when clean: the latest round is the one whose marks come back.
    await api
      .addReading({ session_id: sessionId, paragraph, user_text: round.heard, seconds: elapsed, corrections: round.findings })
      .catch(() => undefined)
  }

  /** Close: the marks stay for clicking. */
  const reset = () => {
    hangUp()
    void endRound()
    roundRef.current = null
    setPhase(null)
    onEnd()
  }

  return { phase, error, heard, seconds, findings, open, audioRef, start: () => void start(), done: () => void done(), reset, ask }
}

/** Starts a round. It stays in its place under the paragraph; the round itself shows below. */
export function ReadAloudButton({ round, disabled }: { round: ReadAloudRound; disabled: boolean }) {
  return (
    <button type="button" className="paragraph-action" onClick={round.start} disabled={disabled || round.phase !== null}>
      {round.phase !== null || round.findings.length > 0 ? 'Read again' : 'Read aloud'}
    </button>
  )
}

/** The round as it runs: the open card, the status bar, and what was heard. */
export function ReadAloudPanel({ round }: { round: ReadAloudRound }) {
  const { phase, error, heard, seconds, findings, open } = round
  const card = open === null ? null : findings[open]
  return (
    <div className={`read-aloud${phase === 'listening' ? ' is-live' : ''}`}>
      <audio ref={round.audioRef} autoPlay />
      {card && <FindingCard finding={card} />}
      {phase !== null && (
        <>
          <div className="read-aloud-bar">
            <span className="read-aloud-status" role="status">
              {STATUS_LABEL[phase]}
            </span>
            {seconds > 0 && <span className="read-aloud-seconds">{seconds}s</span>}
            {phase === 'listening' && (
              <button type="button" onClick={round.done}>
                Done
              </button>
            )}
            {(phase === 'done' || phase === 'failed') && (
              <button type="button" onClick={round.reset}>
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
