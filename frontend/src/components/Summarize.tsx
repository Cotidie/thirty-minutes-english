import { useEffect, useRef, useState } from 'react'
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

interface Props {
  paragraph: string
  sessionId: number
  /** Summaries of this paragraph already kept, oldest first. */
  kept: Summary[]
  onKept: (summary: Summary) => void
  /** Something else holds the microphone. */
  disabled: boolean
  /** The round's status as it moves; null once the slip is gone. */
  onStatus: (status: LiveState['status'] | null) => void
}

/**
 * A button under a paragraph. The reader says what they understood; Gemini's transcription
 * model only writes it down, never shown the paragraph, and on Done a text model judges it
 * against the paragraph: what was missed, what was unskilled in the reader's wording, and the
 * summary with those fixes in.
 */
export function Summarize({ paragraph, sessionId, kept, onKept, disabled, onStatus }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [answer, setAnswer] = useState<SummaryFeedback | null>(null)
  const [writing, setWriting] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const round = useLiveRound(
    audioRef,
    connectSummary,
    async (r) => onKept(await api.addSummary({ session_id: sessionId, paragraph, user_text: r.user.trim(), feedback: answer!, seconds: r.seconds })),
  )
  const { state, close, save } = round
  const level = useMicLevel(round.microphone)
  const status = state?.status ?? null
  const said = state?.user.trim() ?? ''

  useEffect(() => onStatus(status), [status, onStatus])

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
    return round.start()
  }
  const dismiss = () => {
    clear()
    round.dismiss()
  }
  const keep = async () => {
    if (await save()) dismiss()
  }

  return (
    <div className={`summarize${state ? ' is-open' : ''}`}>
      {/* The transcriber sends no sound; the transport still wants somewhere to play it. */}
      <audio ref={audioRef} autoPlay muted />
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
      {state === null ? (
        <button type="button" className="summarize-start" onClick={() => void start()} disabled={disabled}>
          {kept.length > 0 ? 'Summarize again' : 'Summarize'}
        </button>
      ) : (
        <Slip
          label="Summarize this paragraph"
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
          hint={hintFor(state, writing, answer !== null, said !== '')}
          actions={
            <>
              {state.status === 'listening' && (
                <button type="button" onClick={close}>
                  Done
                </button>
              )}
              {state.status === 'closed' && (
                <button type="button" className="slip-save" onClick={() => void keep()} disabled={answer === null}>
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
    </div>
  )
}

/** The judgment: what they missed, their wording fixed line by line, then the summary those fixes add up to. */
function Feedback({ answer }: { answer: SummaryFeedback }) {
  return (
    <div className="summary-feedback">
      {answer.missed.length > 0 && (
        <ul className="summary-missed" aria-label="Missed">
          {answer.missed.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      )}
      {answer.fixes.length > 0 && (
        <ul className="summary-fixes" aria-label="Your wording">
          {answer.fixes.map((fix) => (
            <li key={fix.said}>
              <span className="summary-fix-line">
                <s>{fix.said}</s> <b>{fix.better}</b>
              </span>
              <span className="summary-fix-why">{fix.why}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="summary-better">
        <span className="summary-heading">Put together</span>
        {fixedParts(answer).map((part, i) => (part.fixed ? <b key={i}>{part.text}</b> : part.text))}
        <SpeakButton text={answer.summary} what="the better summary" />
      </p>
    </div>
  )
}

/** The summary cut where a fix's wording sits in it, so the corrected pieces stand out. */
function fixedParts({ summary, fixes }: SummaryFeedback): { text: string; fixed: boolean }[] {
  const lower = summary.toLowerCase()
  const spans = fixes
    .map((fix) => ({ start: lower.indexOf(fix.better.toLowerCase()), length: fix.better.length }))
    .filter((span) => span.start >= 0)
    .sort((a, b) => a.start - b.start)
  const parts: { text: string; fixed: boolean }[] = []
  let at = 0
  for (const span of spans) {
    if (span.start < at) continue // overlaps the one before
    parts.push({ text: summary.slice(at, span.start), fixed: false }, { text: summary.slice(span.start, span.start + span.length), fixed: true })
    at = span.start + span.length
  }
  return [...parts, { text: summary.slice(at), fixed: false }].filter((part) => part.text)
}

function hintFor(state: LiveState, writing: boolean, answered: boolean, said: boolean): string {
  if (writing) return 'Reading your summary against the paragraph…'
  if (state.status === 'listening') return 'In your own words, two or three sentences. Done when you finish'
  if (state.status === 'closed') return answered ? 'Keep it, or ↻ to try again' : said ? '' : 'Nothing came through'
  return ''
}
