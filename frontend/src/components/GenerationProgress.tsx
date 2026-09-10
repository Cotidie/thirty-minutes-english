import { useEffect, useState } from 'react'
import { formatClock } from '../lib/phases'
import { labelFor, percentFor, type JobStatus } from '../lib/progress'

interface Props {
  job: JobStatus
}

export function GenerationProgress({ job }: Props) {
  const [percent, setPercent] = useState(() => percentFor(job))
  useEffect(() => setPercent((prev) => percentFor(job, prev)), [job])

  return (
    <section className="gen" aria-live="polite">
      <div className="gen-row">
        <span className="gen-label">{labelFor(job)}</span>
        <span className="gen-time">
          {formatClock(job.elapsed_seconds)} / about {formatClock(job.expected_seconds)}
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
      <p className="gen-topic">{job.topic}</p>
    </section>
  )
}
