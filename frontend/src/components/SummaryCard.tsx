import type { ReactNode } from 'react'
import './SummaryCard.css'

interface Props {
  /** The small line in the margin: the expression practised, or what was heard. */
  label: ReactNode
  /** The marked line. */
  line: string
  note: ReactNode
}

/** One ledger row of the Summary tab: a label in the margin, the line marked in the column. */
export function SummaryCard({ label, line, note }: Props) {
  return (
    <li className="summary-card">
      <p className="summary-card-label">{label}</p>
      <div className="summary-card-body">
        <p className="summary-card-line">
          <mark>{line}</mark>
        </p>
        <p className="summary-card-note">{note}</p>
      </div>
    </li>
  )
}
