import type { ReactNode } from 'react'
import type { LiveState } from '../lib/liveSession'
import { MicMeter } from './MicMeter'
import './Slip.css'

interface Props {
  label: string
  state: LiveState
  level: number
  status: string
  /** Icon buttons at the right end of the top bar. */
  tools: ReactNode
  /** The captions between the bar and the actions. */
  children: ReactNode
  hint: string
  actions: ReactNode
}

/** The paper slip a live round runs in: meter and status on top, captions, then the hint and buttons. */
export function Slip({ label, state, level, status, tools, children, hint, actions }: Props) {
  return (
    <div className="slip" role="dialog" aria-label={label}>
      <div className="slip-bar">
        {state.status === 'listening' && <MicMeter level={level} />}
        <span className="slip-status" role="status">
          {status}
        </span>
        {state.seconds > 0 && <span className="slip-seconds">{state.seconds}s</span>}
        {tools}
      </div>
      {state.error && <p className="slip-error">{state.error}</p>}
      {children}
      <div className="slip-actions">
        <span className="slip-hint">{hint}</span>
        {actions}
      </div>
    </div>
  )
}
