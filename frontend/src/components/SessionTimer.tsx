import { PHASES, SESSION_SECONDS, formatClock, phaseIndexAt } from '../lib/phases'
import { useSharedTimer } from '../lib/presence/useSharedTimer'
import './SessionTimer.css'

export function SessionTimer() {
  const { elapsed, running, start, pause, reset } = useSharedTimer()
  const phase = phaseIndexAt(elapsed)
  const finished = elapsed >= SESSION_SECONDS
  const progress = elapsed / SESSION_SECONDS

  return (
    <div className="timer" data-presence-anchor="timer">
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
          <button type="button" className="btn btn-ghost" onClick={running ? pause : start}>
            {running ? 'Pause' : elapsed === 0 ? 'Start 30 min' : 'Resume'}
          </button>
        )}
        {elapsed > 0 && (
          <button
            type="button"
            className="btn btn-link"
            onClick={reset}
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
