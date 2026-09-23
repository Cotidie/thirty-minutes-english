import type { Shown, Sound } from '../lib/assessor/judge'
import { nameSound, soundGuide } from '../lib/assessor/sounds'
import './FindingCard.css'

/**
 * One clicked mark, in text: what was said, what it should be, and at most
 * one short tip for the sound that missed worst. The coach says the same two
 * beats aloud.
 */
export function FindingCard({ finding }: { finding: Shown }) {
  return (
    <div className="reading-card" role="note" aria-label={finding.word}>
      <p className="reading-card-head">
        <b>{finding.word}</b>
        {finding.repeated_ok && <span className="read-aloud-ok">✓ read right on the retry</span>}
      </p>
      {finding.kind === 'pronunciation' ? <Said sounds={finding.sounds} /> : <Pause word={finding.word} />}
    </div>
  )
}

function Said({ sounds }: { sounds: Sound[] }) {
  if (sounds.length === 0) return <p className="reading-note">It came out unclear. Say it slowly, one sound at a time.</p>
  const worst = sounds.filter((s) => s.weak).sort((a, b) => a.score - b.score)[0]
  const how = worst && soundGuide(worst.phoneme)?.how
  return (
    <>
      <p className="reading-note">
        You said <Ipa sounds={sounds} said />. It's <Ipa sounds={sounds} />.
      </p>
      {how && (
        <p className="reading-tip">
          {nameSound(worst.phoneme)}: {how}
        </p>
      )}
    </>
  )
}

/** The word in IPA; with `said`, as it was heard, the sounds that missed marked. */
function Ipa({ sounds, said = false }: { sounds: Sound[]; said?: boolean }) {
  return (
    <span className="reading-ipa">
      /
      {sounds.map((s, i) => (
        <span key={i} className={s.weak ? 'is-weak' : undefined}>
          {said && s.weak ? (s.heard ?? '?') : s.phoneme}
        </span>
      ))}
      /
    </span>
  )
}

function Pause({ word }: { word: string }) {
  const [a, b] = word.split(' ')
  return (
    <p className="reading-note">
      You paused between "{a}" and "{b}". It's "{word}" in one breath.
    </p>
  )
}
