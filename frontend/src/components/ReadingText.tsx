import { tokens, type Finding } from '../lib/assessor/judge'

export interface Shown extends Finding {
  /** The reader has since read it right. */
  repeated_ok: boolean
}

interface Props {
  paragraph: string
  findings: Shown[]
  /** Word indices a fluent reader starts a new thought group on: a slash goes before each. */
  breaks?: number[]
  /** Index into `findings` of the one whose card is open. */
  open: number | null
  onOpen: (index: number) => void
}

/**
 * The paragraph word by word. A slash marks where a fluent reader pauses. A
 * mispronounced word is underlined, a pause inside a phrase shows as a bar
 * between the two words; both are buttons that open the finding. Green once
 * the word came out right.
 */
export function ReadingText({ paragraph, findings, breaks = [], open, onOpen }: Props) {
  const words = tokens(paragraph)
  const at = (kind: Finding['kind'], i: number) => findings.findIndex((f) => f.kind === kind && f.at === i)
  return (
    <p className="reading-text" aria-label="Reading">
      {words.map((w, i) => {
        const pause = at('phrasing', i)
        const said = at('pronunciation', i)
        return (
          <span key={i}>
            {i > 0 && ' '}
            {breaks.includes(i) && <span className="reading-break" aria-label="pause">/</span>}
            {breaks.includes(i) && ' '}
            {pause >= 0 && <Hit finding={findings[pause]} open={open === pause} onClick={() => onOpen(pause)} label="|" />}
            {pause >= 0 && ' '}
            {said >= 0 ? <Hit finding={findings[said]} open={open === said} onClick={() => onOpen(said)} label={w} /> : w}
          </span>
        )
      })}
    </p>
  )
}

function Hit({ finding, open, onClick, label }: { finding: Shown; open: boolean; onClick: () => void; label: string }) {
  const title = finding.kind === 'phrasing' ? `pause inside "${finding.word}"` : `${finding.word}: ${finding.heard}`
  return (
    <button
      type="button"
      className={`reading-hit is-${finding.kind}${finding.repeated_ok ? ' is-ok' : ''}${open ? ' is-open' : ''}`}
      title={title}
      aria-label={title}
      onClick={onClick}
    >
      {label}
    </button>
  )
}
