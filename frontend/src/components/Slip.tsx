import type { ReactNode } from 'react'
import type { LiveState } from '../lib/liveSession'
import { MicMeter } from './MicMeter'
import './Slip.css'

interface Props {
  label: string
  className?: string
  state: LiveState
  level: number
  status: string
  /** Icon buttons at the right end of the top bar. */
  tools?: ReactNode
  /** The captions between the bar and the actions. */
  children?: ReactNode
  hint: string
  actions: ReactNode
}

/** The paper slip a live round runs in: meter and status on top, captions, then the hint and buttons. */
export function Slip({ label, className, state, level, status, tools, children, hint, actions }: Props) {
  return (
    <div className={`ask-slip${className ? ` ${className}` : ''}`} role="dialog" aria-label={label}>
      <div className="ask-bar">
        {state.status === 'listening' && <MicMeter level={level} />}
        <span className="ask-status" role="status">
          {status}
        </span>
        {state.seconds > 0 && <span className="ask-seconds">{state.seconds}s</span>}
        {tools}
      </div>
      {state.error && <p className="ask-error">{state.error}</p>}
      {children}
      <div className="ask-actions">
        <span className="ask-hint">{hint}</span>
        {actions}
      </div>
    </div>
  )
}
