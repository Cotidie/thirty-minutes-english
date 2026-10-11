import { useEffect, useState } from 'react'
import { formatClock } from '../lib/phases'
import { labelFor, metaFor, percentFor, type JobStatus } from '../lib/progress'
import './GenerationProgress.css'

interface Props {
  job: JobStatus
  /** Cancels a running job; dismisses a failed one. */
  onClose: () => void
}

/** A failed job keeps its bar where it stopped and shows the error until the user closes it. */
export function GenerationProgress({ job, onClose }: Props) {
  const [percent, setPercent] = useState(() => percentFor(job))
  useEffect(() => setPercent((prev) => percentFor(job, prev)), [job])
  const failed = job.status === 'failed'

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
        {(failed || job.status === 'running') && (
          <button type="button" className="btn btn-link" onClick={onClose}>
            {failed ? 'Close' : 'Cancel'}
          </button>
        )}
      </div>
      <p className="gen-topic">{job.topic}</p>
    </section>
  )
}
