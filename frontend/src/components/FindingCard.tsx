import type { Sound } from '../lib/assessor/judge'
import { nameSound, soundGuide } from '../lib/assessor/sounds'
import type { Shown } from './ReadingText'

/**
 * Everything the assessor knows about one clicked mark, in text. The coach
 * says two beats; this is the full account: the word's sounds against what
 * was heard, and where the mouth goes for each one that missed.
 */
export function FindingCard({ finding }: { finding: Shown }) {
  return (
    <div className="reading-card" role="note" aria-label={finding.word}>
      <p className="reading-card-head">
        <b>{finding.word}</b>
        {finding.kind === 'pronunciation' ? (
          <>
            <span className="reading-ipa">/{finding.sounds.map((s) => s.phoneme).join('')}/</span>
            <span className="reading-score">{finding.score} / 100</span>
          </>
        ) : (
          finding.score > 0 && <span className="reading-score">paused {(finding.score / 1000).toFixed(1)} s</span>
        )}
        {finding.repeated_ok && <span className="read-aloud-ok">✓ read right on the retry</span>}
      </p>
      {finding.kind === 'pronunciation' ? <Sounds sounds={finding.sounds} /> : <Pause word={finding.word} />}
    </div>
  )
}

function Sounds({ sounds }: { sounds: Sound[] }) {
  const weak = sounds.filter((s) => s.weak)
  if (sounds.length === 0) return <p className="reading-note">The word came out unclear. Say it slowly, one sound at a time.</p>
  return (
    <>
      <dl className="reading-sounds">
        <dt>Target</dt>
        <dd>
          {sounds.map((s, i) => (
            <span key={i} className={s.weak ? 'is-weak' : undefined}>
              {s.phoneme}
            </span>
          ))}
        </dd>
        <dt>You</dt>
        <dd>
          {sounds.map((s, i) => (
            <span key={i} className={s.weak ? 'is-weak' : undefined}>
              {s.weak ? (s.heard ?? '?') : s.phoneme}
            </span>
          ))}
        </dd>
      </dl>
      <ul className="reading-tips">
        {weak.map((s, i) => (
          <li key={i}>
            <b>{nameSound(s.phoneme)}</b>
            {s.heard ? `: you said ${nameSound(s.heard)}.` : ' came out unclear.'} {soundGuide(s.phoneme)?.how}
          </li>
        ))}
      </ul>
    </>
  )
}

function Pause({ word }: { word: string }) {
  const [a, b] = word.split(' ')
  return (
    <p className="reading-note">
      You paused between "{a}" and "{b}". They belong to one thought group: read "{word}" in one breath, no gap, and keep the
      voice moving into "{b}".
    </p>
  )
}
