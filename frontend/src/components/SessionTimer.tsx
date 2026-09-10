import { useEffect, useRef, useState } from 'react'
import { PHASES, SESSION_SECONDS, formatClock, phaseIndexAt } from '../lib/phases'

interface Props {
  onPhaseChange: (index: number) => void
}

export function SessionTimer({ onPhaseChange }: Props) {
  const [elapsed, setElapsed] = useState(0)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setElapsed((e) => Math.min(SESSION_SECONDS, e + 1)), 1000)
    return () => window.clearInterval(id)
  }, [running])

  const phase = phaseIndexAt(elapsed)
  const notifiedPhase = useRef<number | null>(null)
  useEffect(() => {
    if (elapsed === 0) {
      notifiedPhase.current = null
      return
    }
    if (notifiedPhase.current !== phase) {
      notifiedPhase.current = phase
      onPhaseChange(phase)
    }
  }, [phase, elapsed, onPhaseChange])

  const finished = elapsed >= SESSION_SECONDS
  const progress = elapsed / SESSION_SECONDS

  return (
    <div className="timer">
      <div className="timer-clock" aria-live="off">
        {formatClock(SESSION_SECONDS - elapsed)}
      </div>
      <div className="timer-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
        {PHASES.map((p, i) => (
          <span key={p.key} className={`timer-segment${i === phase && elapsed > 0 ? ' is-active' : ''}`} style={{ flex: p.minutes }}>
            <span className="timer-fill" style={{ width: `${segmentFill(elapsed, i) * 100}%` }} />
          </span>
        ))}
      </div>
      <div className="timer-actions">
        {finished ? (
          <span className="timer-done">Time. Well done.</span>
        ) : (
          <button type="button" className="btn btn-ghost" onClick={() => setRunning((r) => !r)}>
            {running ? 'Pause' : elapsed === 0 ? 'Start 30 min' : 'Resume'}
          </button>
        )}
        {elapsed > 0 && (
          <button
            type="button"
            className="btn btn-link"
            onClick={() => {
              setRunning(false)
              setElapsed(0)
            }}
          >
            Reset
          </button>
        )}
      </div>
    </div>
  )
}

function segmentFill(elapsed: number, index: number): number {
  const start = PHASES.slice(0, index).reduce((s, p) => s + p.minutes * 60, 0)
  const length = PHASES[index].minutes * 60
  return Math.min(1, Math.max(0, (elapsed - start) / length))
}
