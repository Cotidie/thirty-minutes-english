import { useEffect, useRef, useState, type RefObject } from 'react'
import { api } from '../api'
import { connectSummary } from '../lib/liveClient'
import type { LiveState } from '../lib/liveSession'
import { useMicLevel } from '../lib/micLevel'
import { useLiveRound } from '../lib/useLiveRound'
import type { Summary, SummaryFeedback } from '../types'
import { Slip } from './Slip'
import { SpeakButton } from './SpeakButton'
import './Summarize.css'

const STATUS_LABEL: Record<LiveState['status'], string> = {
  connecting: 'Connecting…',
  listening: 'Say what this paragraph is about',
  closing: 'Wrapping up…',
  closed: 'Summary in',
  failed: 'Could not start',
}

interface Options {
  paragraph: string
  sessionId: number
  onKept: (summary: Summary) => void
  onStart: () => void
  /** The microphone is free. */
  onEnd: () => void
}

/** A paragraph's summary round as the page sees it. */
export interface SummaryRound {
  state: LiveState | null
  audioRef: RefObject<HTMLAudioElement | null>
  level: number
  /** What was said, final once the round is closed. */
  said: string
  answer: SummaryFeedback | null
  writing: boolean
  failure: string | null
  start: () => void
  close: () => void
  dismiss: () => void
  keep: () => void
}

/**
 * One round of the summary coach (agents/summary-coach/AGENT.md): the reader says what the paragraph
 * is about with it in view, Gemini's transcription model writes it down primed with the paragraph's
 * words, and on Done the judge answers in one fixed shape.
 */
export function useSummary({ paragraph, sessionId, onKept, onStart, onEnd }: Options): SummaryRound {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [answer, setAnswer] = useState<SummaryFeedback | null>(null)
  const [writing, setWriting] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const round = useLiveRound(
    audioRef,
    (opts) => connectSummary(paragraph, opts),
    async (r) => onKept(await api.addSummary({ session_id: sessionId, paragraph, user_text: r.user.trim(), feedback: answer!, seconds: r.seconds })),
  )
  const { state } = round
  const level = useMicLevel(round.microphone)
  const status = state?.status ?? null
  const said = state?.user.trim() ?? ''

  // The round is over and something was said: have it judged, once.
  useEffect(() => {
    if (status !== 'closed' || !said) return
    let live = true
    setWriting(true)
    api
      .summaryFeedback(paragraph, said)
      .then((written) => live && setAnswer(written))
      .catch((e: Error) => live && setFailure(e.message))
      .finally(() => live && setWriting(false))
    return () => {
      live = false
    }
    // `said` is final once the round is closed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  const clear = () => {
    setAnswer(null)
    setWriting(false)
    setFailure(null)
  }
  const start = () => {
    clear()
    onStart()
    void round.start()
  }
  const dismiss = () => {
    clear()
    round.dismiss()
    onEnd()
  }
  const keep = async () => {
    if (await round.save()) dismiss()
  }

  return { state, audioRef, level, said, answer, writing, failure, start, close: round.close, dismiss, keep: () => void keep() }
}

/** Starts a round. It stays in its place under the paragraph; the round itself shows below. */
export function SummarizeButton({ summary, kept, disabled }: { summary: SummaryRound; kept: boolean; disabled: boolean }) {
  return (
    <button type="button" className="paragraph-action" onClick={summary.start} disabled={disabled || summary.state !== null}>
      {kept ? 'Summarize again' : 'Summarize'}
    </button>
  )
}

/** The round as it runs, then the summaries already kept. */
export function SummaryPanel({ summary, kept }: { summary: SummaryRound; kept: Summary[] }) {
  const { state, said, answer, writing, failure } = summary
  return (
    <div className="summarize">
      {/* The transcriber sends no sound; the transport still wants somewhere to play it. */}
      <audio ref={summary.audioRef} autoPlay muted />
      {state && (
        <Slip
          label="Summarize this paragraph"
          state={state}
          level={summary.level}
          status={STATUS_LABEL[state.status]}
          tools={
            <>
              <button type="button" className="slip-icon" aria-label="Retry" title="Retry" onClick={summary.start}>
                ↻
              </button>
              <button type="button" className="slip-icon" aria-label="Discard" title="Discard" onClick={summary.dismiss}>
                ✕
              </button>
            </>
          }
          hint={hintFor(state, writing, answer !== null, said !== '')}
          actions={
            <>
              {state.status === 'listening' && (
                <button type="button" onClick={summary.close}>
                  Done
                </button>
              )}
              {state.status === 'closed' && (
                <button type="button" className="slip-save" onClick={summary.keep} disabled={answer === null}>
                  Keep
                </button>
              )}
            </>
          }
        >
          {failure && <p className="slip-error">{failure}</p>}
          {said && (
            <dl className="slip-captions">
              <dt>You</dt>
              <dd>{said}</dd>
            </dl>
          )}
          {answer && <Feedback answer={answer} />}
        </Slip>
      )}
      {kept.length > 0 && (
        <ol className="summaries" aria-label="Summaries of this paragraph">
          {kept.map((s) => (
            <li key={s.id} className="summary-kept">
              <p className="summary-kept-said">{s.user_text}</p>
              <p className="summary-kept-better">{s.feedback.summary}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** The judgment in one fixed shape, read at a glance: the point missed, up to two wordings bettered, the model answer. */
function Feedback({ answer }: { answer: SummaryFeedback }) {
  return (
    <dl className="summary-feedback">
      {answer.missed.length > 0 && (
        <>
          <dt>Missed</dt>
          <dd className="summary-missed">{answer.missed[0]}</dd>
        </>
      )}
      {answer.fixes.length > 0 && (
        <>
          <dt>Say it better</dt>
          <dd>
            {answer.fixes.map((fix) => (
              <span key={fix.said} className="summary-fix">
                <s>{fix.said}</s> → <b>{fix.better}</b>
              </span>
            ))}
          </dd>
        </>
      )}
      <dt>Model answer</dt>
      <dd className="summary-better">
        {answer.summary}
        <SpeakButton text={answer.summary} what="the model answer" />
      </dd>
    </dl>
  )
}

function hintFor(state: LiveState, writing: boolean, answered: boolean, said: boolean): string {
  if (writing) return 'Reading your summary against the paragraph…'
  if (state.status === 'listening') return 'In your own words, two or three sentences. Done when you finish'
  if (state.status === 'closed') return answered ? 'Keep it, or ↻ to try again' : said ? '' : 'Nothing came through'
  return ''
}
