import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { api } from '../api'
import { startAzureAssessor, type Assessor } from '../lib/assessor/azure'
import { Judge, type AzureWord, type Shown } from '../lib/assessor/judge'
import { connectReadAloud, type LiveConnection } from '../lib/liveClient'
import { personColor, type SharedRound } from '../lib/presence/store'
import { useShareRound, type useOthersRound } from '../lib/presence/useSharedRound'
import { useSharedView } from '../lib/presence/useSharedView'
import { usePrice } from '../lib/usePrice'
import type { Paragraph, Reading } from '../types'
import { FindingCard } from './FindingCard'
import { Price } from './Price'
import './ReadAloud.css'

interface Options {
  /** The paragraph read; a finished round is filed under its id. */
  paragraph: Paragraph
  /** The marks shown while this page runs no round of its own: someone else's round on this paragraph, else the last one saved. */
  saved: Shown[]
  /** The round this page read is filed. */
  onFiled: (reading: Reading) => void
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
/** No word at all from the coach by then: hang up anyway, and it costs nothing. */
export const COACH_TIMEOUT_MS = 15_000

/** The reading: the microphone, Azure on it, and the judge's verdicts on the paragraph. */
interface Round {
  microphone: MediaStream
  assessor: Assessor | null
  judge: Judge
  findings: Shown[]
  heard: string
  startedAt: number
  /** Done was clicked: what Azure still hands over while it stops belongs to a finished round. */
  over: boolean
}

/** One coach call for one clicked mark: opened, spoken, hung up. */
interface Call {
  coach: LiveConnection
  timer: ReturnType<typeof setTimeout> | null
  /** Whether it has said a word yet. */
  spoke: boolean
}

/**
 * Read aloud with the assessor as the only listener. Azure marks the paragraph
 * as the reader goes; a clicked mark opens the full account in text, and the
 * coach is dialled to say its two beats and hang up.
 */
export function useReadAloud({ paragraph: { id: paragraphId, text: paragraph }, saved, onFiled, onStart, onEnd }: Options): ReadAloudRound {
  const [phase, setPhase] = useState<Phase | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [heard, setHeard] = useState('')
  const [seconds, setSeconds] = useState(0)
  /** The marks of a round started on this page, until it is closed; otherwise the saved ones show. */
  const [fresh, setFresh] = useState<Shown[] | null>(null)
  const findings = fresh ?? saved
  /** Whichever mark anyone in the session opened last. */
  const [open, setOpen] = useSharedView<number | null>(`mark:${paragraphId}`, null)
  const share = useShareRound()
  /** This paragraph's round is the one the others see. A connection shares one round, so no other paragraph may end it. */
  const sharing = useRef(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const roundRef = useRef<Round | null>(null)
  const callRef = useRef<Call | null>(null)
  /** Stops a coach call still connecting: nothing else can, until `callRef` has it. */
  const calling = useRef<AbortController | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      calling.current?.abort()
      hangUp()
      void endRound()
    }
  }, [])

  /** Tells the others how this paragraph's round stands, or that it is over. */
  const shareRound = (round: Omit<SharedRound, 'paragraph'> | null) => {
    if (round === null && !sharing.current) return
    sharing.current = round !== null
    share(round && { paragraph: paragraphId, ...round })
  }

  // Leaving the page ends the round for the others too.
  useEffect(
    () => () => {
      if (sharing.current) share(null)
    },
    [share],
  )

  const stopIfLeft = () => {
    if (!mounted.current) throw new Error('The page was left before the round started')
  }

  const start = async () => {
    onStart()
    shareRound({ phase: 'reading', heard: '', findings: [] })
    setPhase('connecting')
    setError(null)
    setHeard('')
    setSeconds(0)
    setFresh([])
    setOpen(null)
    let microphone: MediaStream | null = null
    let hold: number | null = null
    const giveBack = () => {
      if (hold !== null) void api.giveBackHold(hold)
      hold = null
    }
    try {
      // The microphone first: a refused one spends nothing.
      microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
      stopIfLeft()
      const session = await api.assessorToken()
      hold = session.hold
      stopIfLeft()
      const round: Round = {
        microphone,
        assessor: null,
        judge: new Judge(session.word_score, paragraph),
        findings: [],
        heard: '',
        startedAt: Date.now(),
        over: false,
      }
      roundRef.current = round
      round.assessor = await startAzureAssessor({
        microphone,
        paragraph,
        session,
        onSegment: (words, text) => judged(round, words, text),
        onError: (message) => {
          setError(`Assessor: ${message}`)
          giveBack()
        },
      })
      stopIfLeft()
      if (hold !== null) void api.confirmHold(hold)
      setPhase('listening')
    } catch (e) {
      microphone?.getTracks().forEach((t) => t.stop())
      void endRound()
      giveBack()
      shareRound(null)
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
    shareRound({ phase: round.over ? 'done' : 'reading', heard: round.heard, findings: round.findings })
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
    calling.current?.abort()
    const call = new AbortController()
    calling.current = call
    const { signal } = call
    // Gemini reports session.started while connecting, before `coach` exists.
    let coach: LiveConnection | null = null
    let started = false
    try {
      coach = await connectReadAloud(paragraph, {
        audio: audioRef.current!,
        signal,
        onEvent: (event) => {
          if (signal.aborted) return
          if (event.type === 'session.started') {
            started = true
            coach?.correct(finding)
          }
          if (event.type === 'session.output_transcript.delta') {
            if (callRef.current) callRef.current.spoke = true
            linger(COACH_SILENCE_MS)
          }
          if (event.type === 'session.closed') hangUp()
        },
        onDisconnect: () => {
          if (!signal.aborted) hangUp()
        },
      })
      if (signal.aborted) {
        coach.giveBack()
        coach.dispose()
        return
      }
      // The coach only speaks here; what the reader says next is Azure's to judge.
      coach.microphone.getAudioTracks().forEach((t) => (t.enabled = false))
      callRef.current = { coach, timer: null, spoke: false }
      if (started) coach.correct(finding)
      linger(COACH_TIMEOUT_MS)
    } catch (e) {
      if (!signal.aborted) setError(e instanceof Error ? e.message : String(e))
    }
  }

  /** Hang up once the coach has been quiet this long. */
  const linger = (ms: number) => {
    const call = callRef.current
    if (!call) return
    if (call.timer) clearTimeout(call.timer)
    call.timer = setTimeout(() => {
      if (!call.spoke) call.coach.giveBack()
      call.coach.close()
    }, ms)
  }

  const hangUp = () => {
    const call = callRef.current
    if (!call) return
    callRef.current = null
    if (call.timer) clearTimeout(call.timer)
    if (!call.spoke) call.coach.giveBack()
    call.coach.dispose()
  }

  /** The reader is done: the round is filed; the marks stay clickable. */
  const done = async () => {
    const round = roundRef.current
    if (!round) return
    const elapsed = Math.round((Date.now() - round.startedAt) / 1000)
    setSeconds(elapsed)
    setPhase('done')
    round.over = true
    shareRound({ phase: 'done', heard: round.heard, findings: round.findings })
    await endRound()
    // Filed even when clean: the latest round is the one whose marks come back.
    await api
      .addReading({ paragraph_id: paragraphId, user_text: round.heard, seconds: elapsed, corrections: round.findings })
      .then(onFiled)
      .catch(() => undefined)
  }

  /** Close: the marks stay for clicking. */
  const reset = () => {
    hangUp()
    void endRound()
    roundRef.current = null
    setPhase(null)
    setFresh(null)
    shareRound(null)
    onEnd()
  }

  return { phase, error, heard, seconds, findings, open, audioRef, start: () => void start(), done: () => void done(), reset, ask }
}

/** Starts a round. It stays in its place under the paragraph; the round itself shows below. While someone else reads,
 * it is off and says who. */
export function ReadAloudButton({ round, disabled, reader }: { round: ReadAloudRound; disabled: boolean; reader: string | null }) {
  const { price, short } = usePrice('read_aloud_token')
  return (
    <button
      type="button"
      className="paragraph-action"
      onClick={round.start}
      disabled={disabled || reader !== null || round.phase !== null || short !== null}
      title={(reader ? `${reader} is reading` : short) ?? undefined}
    >
      {round.phase !== null || round.findings.length > 0 ? 'Read again' : 'Read aloud'}
      <Price amount={price} />
    </button>
  )
}

/** The round as it runs: the open card, the status bar, and what was heard. With no round of mine, someone else's. */
export function ReadAloudPanel({ round, watched }: { round: ReadAloudRound; watched: ReturnType<typeof useOthersRound> }) {
  const { phase, error, heard, seconds, findings, open } = round
  const card = open === null ? null : findings[open]
  if (phase === null && watched) return <WatchedRound watched={watched} card={card} audioRef={round.audioRef} />
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

/** Someone else's round on this paragraph, as they read it: their name in their color, and what was heard. */
function WatchedRound({ watched, card, audioRef }: { watched: NonNullable<ReturnType<typeof useOthersRound>>; card: Shown | null | undefined; audioRef: RefObject<HTMLAudioElement | null> }) {
  const { name, color, round: theirs } = watched
  return (
    <div className="read-aloud is-watching" style={{ '--person': personColor(color) } as CSSProperties}>
      {/* A mark of theirs that I click is spoken here, to me. */}
      <audio ref={audioRef} autoPlay />
      {card && <FindingCard finding={card} />}
      <div className="read-aloud-bar">
        <span className="read-aloud-status" role="status">
          {theirs.phase === 'reading' ? `${name} is reading.` : `${name} finished. Click a mark to hear it.`}
        </span>
      </div>
      {theirs.heard && (
        <dl className="read-aloud-captions">
          <dt>{name}</dt>
          <dd>{theirs.heard}</dd>
        </dl>
      )}
    </div>
  )
}
