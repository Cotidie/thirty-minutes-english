import { useEffect, useRef, useState, type RefObject } from 'react'
import { api } from '../api'
import { connectSummary } from '../lib/liveClient'
import type { LiveState } from '../lib/liveSession'
import { useMicLevel } from '../lib/micLevel'
import { speakerOf } from '../lib/speaker'
import { useLiveRound } from '../lib/useLiveRound'
import { usePrice } from '../lib/usePrice'
import type { Paragraph, Summary, SummaryFeedback } from '../types'
import { Price } from './Price'
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
  /** The paragraph summed up; the kept summary is filed under its id. */
  paragraph: Paragraph
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
  /** Being judged and kept. */
  writing: boolean
  failure: string | null
  start: () => void
  close: () => void
  dismiss: () => void
}

/**
 * One round of the summary coach (agents/summary-coach/AGENT.md): the reader says what the paragraph
 * is about with it in view, Gemini's transcription model writes it down primed with the paragraph's
 * words, and on Done the summary goes to the server, which judges it in the background. The paragraph
 * is free again as soon as the server has it; the feedback reaches the card under it later.
 */
export function useSummary({ paragraph: { id: paragraphId, text: paragraph }, onKept, onStart, onEnd }: Options): SummaryRound {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [writing, setWriting] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const round = useLiveRound(audioRef, (opts) => connectSummary(paragraph, opts))
  const { state, giveBack } = round
  const level = useMicLevel(round.microphone)
  const status = state?.status ?? null
  const said = state?.user.trim() ?? ''
  const mounted = useRef(true)
  // A round under way whose summary has not gone to the server: leaving the page gives its price back.
  const unsent = useRef(false)
  // Which round's summary is being sent; a Retry or Discard meanwhile leaves the screen to the new one.
  const sending = useRef(0)

  const clear = () => {
    sending.current += 1
    setWriting(false)
    setFailure(null)
  }
  const start = () => {
    clear()
    unsent.current = true
    onStart()
    void round.start()
  }
  const dismiss = () => {
    clear()
    unsent.current = false
    round.dismiss()
    onEnd()
  }

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (unsent.current) giveBack()
    }
  }, [giveBack])

  // The round is over and something was said: send it once. Once the server has it, the slip closes and the
  // paragraph is free; the request is never dropped, even if the page is left before it answers.
  useEffect(() => {
    if (status !== 'closed' || !said) return
    unsent.current = false
    const request = sending.current
    const current = () => mounted.current && sending.current === request
    setWriting(true)
    api
      .addSummary({ paragraph_id: paragraphId, user_text: said, seconds: state!.seconds })
      .then((summary) => {
        if (!mounted.current) return
        onKept(summary)
        if (current()) dismiss()
      })
      .catch((e: Error) => {
        // The server does not have what was said, so the round did not deliver. A newer round's price is not this one's.
        if (sending.current === request) giveBack()
        if (current()) setFailure(e.message)
      })
      .finally(() => current() && setWriting(false))
    // `said` is final once the round is closed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  return { state, audioRef, level, said, writing, failure, start, close: round.close, dismiss }
}

/** Starts a round. It stays in its place under the paragraph; the round itself shows below. While someone else reads
 * aloud, it is off and says who. */
export function SummarizeButton({ summary, kept, disabled, reader }: { summary: SummaryRound; kept: boolean; disabled: boolean; reader: string | null }) {
  const { price, short } = usePrice('summary_voice', 'summary_feedback')
  return (
    <button
      type="button"
      className="paragraph-action"
      onClick={summary.start}
      disabled={disabled || reader !== null || summary.state !== null || short !== null}
      title={(reader ? `${reader} is reading` : short) ?? undefined}
    >
      {kept ? 'Summarize again' : 'Summarize'}
      <Price amount={price} />
    </button>
  )
}

/** The round as it runs, then the summaries already kept, newest first, each in its card. */
export function SummaryPanel({ summary, kept }: { summary: SummaryRound; kept: Summary[] }) {
  const { state, said, writing, failure } = summary
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
          hint={hintFor(state, writing, said !== '')}
          actions={
            state.status === 'listening' && (
              <button type="button" onClick={summary.close}>
                Done
              </button>
            )
          }
        >
          {failure && <p className="slip-error">{failure}</p>}
          {said && (
            <dl className="slip-captions">
              <dt>You</dt>
              <dd>{said}</dd>
            </dl>
          )}
        </Slip>
      )}
      {kept.length > 0 && (
        <ol className="summaries" aria-label="Summaries of this paragraph">
          {[...kept].reverse().map((s) => (
            <li key={s.id} className="slip">
              <dl className="slip-captions">
                <dt>{speakerOf(s)}</dt>
                <dd>{s.user_text}</dd>
              </dl>
              <Judgment summary={s} />
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/** Where a kept summary's feedback is: still coming, not to be had, or in. */
function Judgment({ summary }: { summary: Summary }) {
  if (summary.status === 'judging') return <p className="summary-judging">Reading your summary against the paragraph…</p>
  if (summary.status === 'failed' || !summary.feedback) return <FailedJudgment summary={summary} />
  return <Feedback answer={summary.feedback} />
}

/** Why the feedback failed, and a way to judge the same words again or drop them. Whoever judges again pays. */
function FailedJudgment({ summary }: { summary: Summary }) {
  const { price, short } = usePrice('summary_feedback')
  const [error, setError] = useState<string | null>(null)
  const act = (call: () => Promise<unknown>) => {
    setError(null)
    call().catch((e: Error) => setError(e.message))
  }
  return (
    <div className="summary-failed">
      <p className="slip-error">{summary.error}</p>
      {error && <p className="slip-error">{error}</p>}
      <div className="summary-failed-actions">
        <button
          type="button"
          className="paragraph-action"
          onClick={() => act(() => api.judgeSummaryAgain(summary.id))}
          disabled={short !== null}
          title={short ?? undefined}
        >
          Judge again
          <Price amount={price} />
        </button>
        <button type="button" className="paragraph-action" onClick={() => act(() => api.removeSummary(summary.id))}>
          Remove
        </button>
      </div>
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
                <span className="summary-said">{fix.said}</span> → <b>{fix.better}</b>
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

function hintFor(state: LiveState, writing: boolean, said: boolean): string {
  if (writing) return 'Sending your summary…'
  if (state.status === 'listening') return 'In your own words, two or three sentences. Done when you finish'
  if (state.status === 'closed' && !said) return 'Nothing came through'
  return ''
}
