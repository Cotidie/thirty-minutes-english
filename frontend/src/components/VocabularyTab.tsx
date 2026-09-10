import { useState } from 'react'
import type { VocabularyItem } from '../types'

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

export function VocabularyTab({ items }: { items: VocabularyItem[] }) {
  return (
    <section className="tab-panel">
      <p className="tab-brief">
        Take turns. Read the word and its sentence aloud, then explain in English what you think it means. Check only
        after both of you have tried.
      </p>
      <div className="vocab-grid">
        {items.map((item) => (
          <VocabCard key={item.word} item={item} />
        ))}
      </div>
    </section>
  )
}
