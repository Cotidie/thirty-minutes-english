import { useState } from 'react'
import { practiceWord, type Example, type VocabularyItem } from '../types'
import { Practice } from './Practice'
import { StarButton } from './StarButton'

function VocabCard({ item }: { item: VocabularyItem }) {
  const [revealed, setRevealed] = useState(false)
  return (
    <button
      type="button"
      className={`vocab-card${revealed ? ' is-revealed' : ''}`}
      aria-expanded={revealed}
      onClick={() => setRevealed((r) => !r)}
    >
      <span className="vocab-word">
        <span className="vocab-word-text">{item.word}</span> <em className="vocab-pos">{item.pos}</em>
      </span>
      <span className="vocab-example">{item.example}</span>
      <span className="vocab-definition" aria-hidden={!revealed}>
        {revealed ? item.definition : 'Tap to check the meaning'}
      </span>
    </button>
  )
}

interface Props {
  items: VocabularyItem[]
  sessionId: number
  starred: string[]
  onToggleStar: (word: string) => void
  /** Every sentence made in this session; each word shows its own. */
  examples: Example[]
  onExample: (example: Example) => void
}

export function VocabularyTab({ items, sessionId, starred, onToggleStar, examples, onExample }: Props) {
  return (
    <section className="tab-panel is-wide">
      <p className="tab-brief">
        Take turns. Read the word and its sentence aloud, then explain in English what you think it means. Check only
        after both of you have tried.
      </p>
      <div className="vocab-grid">
        {items.map((item) => (
          <div key={item.word} className="vocab-cell">
            <VocabCard item={item} />
            <StarButton label={item.word} on={starred.includes(item.word)} onToggle={() => onToggleStar(item.word)} />
            <Practice
              target={practiceWord(item)}
              label="Practice"
              sessionId={sessionId}
              examples={examples.filter((e) => e.expression === item.word)}
              onKept={onExample}
            />
          </div>
        ))}
      </div>
    </section>
  )
}
