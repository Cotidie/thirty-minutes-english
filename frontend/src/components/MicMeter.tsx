import { LEVEL_STEPS } from '../lib/micLevel'

/** Five bars that fill with how loud the microphone is, so silence is visible. */
export function MicMeter({ level }: { level: number }) {
  return (
    <span className={`ask-level${level === 0 ? ' is-quiet' : ''}`} aria-hidden="true">
      {Array.from({ length: LEVEL_STEPS }, (_, i) => (
        <i key={i} className={i < level ? 'is-on' : ''} />
      ))}
    </span>
  )
}
