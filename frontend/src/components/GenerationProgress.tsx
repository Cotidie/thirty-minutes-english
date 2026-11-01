import { useEffect, useState } from 'react'
import { useCredits } from '../lib/credits'
import { formatClock } from '../lib/phases'
import { labelFor, metaFor, percentFor, type JobStatus } from '../lib/progress'
import { Price } from './Price'
import './GenerationProgress.css'

interface Props {
  job: JobStatus
  /** Cancels a running job; dismisses a failed one. */
  onClose: () => void
  /** Opens the session the job has saved; its pictures may still be on their way. */
  onOpen: (sessionId: number) => void
}

/** What stopping a running job comes to, for the button that does it. */
function stopNote(job: JobStatus, price: number): string | undefined {
  if (job.session_id !== null) {
    return price > 0 ? `Stops now. The session is deleted and ${price} credits stay charged.` : 'Stops now. The session is deleted.'
  }
  return job.spent && price > 0 ? `Stops now. ${price} credits stay charged.` : undefined
}

/** A failed job keeps its bar where it stopped and shows the error until the user closes it. */
export function GenerationProgress({ job, onClose, onOpen }: Props) {
  const [percent, setPercent] = useState(() => percentFor(job))
  useEffect(() => setPercent((prev) => percentFor(job, prev)), [job])
  const failed = job.status === 'failed'
  const price = useCredits().cost('session_cancelled')
  const note = stopNote(job, price)

  return (
    <section className={failed ? 'gen gen-failed' : 'gen'} aria-live="polite">
      <div className="gen-row">
        <span className="gen-label">{labelFor(job)}</span>
        <span className="gen-time">
          {failed
            ? `after ${formatClock(job.elapsed_seconds)}`
            : `${formatClock(job.elapsed_seconds)} / about ${formatClock(job.expected_seconds)}`}
        </span>
      </div>
      <div
        className="gen-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label="Generation progress"
      >
        <div className="gen-fill" style={{ width: `${percent}%` }} />
      </div>
      {failed && (
        <pre className="gen-error" role="alert">
          {job.error ?? 'generation failed'}
        </pre>
      )}
      <div className="gen-row">
        <span className="gen-meta">{metaFor(job)}</span>
        {job.session_id !== null && (
          <button type="button" className="btn btn-link" onClick={() => onOpen(job.session_id as number)}>
            Open session
          </button>
        )}
        {failed && (
          <button type="button" className="btn btn-link" onClick={onClose}>
            Close
          </button>
        )}
        {job.status === 'running' && (
          <button
            type="button"
            className="btn btn-link"
            onClick={() => {
              if (!note || window.confirm(note)) onClose()
            }}
            title={note}
          >
            {job.session_id === null ? 'Cancel' : 'Cancel and delete'}
            {job.spent && <Price amount={price} />}
          </button>
        )}
      </div>
      <p className="gen-topic">{job.topic}</p>
    </section>
  )
}
