import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FindingCard } from './FindingCard'

describe('FindingCard', () => {
  it('says what was heard, what it should be, and one tip for the worst sound', () => {
    render(
      <FindingCard
        finding={{
          kind: 'pronunciation',
          word: 'answered',
          heard: 'ɪ for æ',
          fix: 'ænsɚd',
          at: 12,
          score: 42,
          repeated_ok: false,
          sounds: [
            { phoneme: 'æ', score: 11, weak: true, heard: 'ɪ' },
            { phoneme: 'n', score: 90, weak: false },
            { phoneme: 's', score: 88, weak: false },
            { phoneme: 'ɚ', score: 30, weak: true },
            { phoneme: 'd', score: 85, weak: false },
          ],
        }}
      />,
    )
    const card = screen.getByRole('note', { name: 'answered' })
    expect(card.querySelector('.reading-note')?.textContent).toBe("You said /ɪns?d/. It's /ænsɚd/.")
    expect([...card.querySelectorAll('.is-weak')].map((s) => s.textContent)).toEqual(['ɪ', '?', 'æ', 'ɚ'])
    expect(card.querySelector('.reading-tip')?.textContent).toBe('æ as in cAt: Jaw drops, mouth wide, tongue low and front. Longer than "e".')
  })

  it('explains a pause inside a phrase, and notes a retry that came out right', () => {
    render(
      <FindingCard
        finding={{ kind: 'phrasing', word: 'July 1969', heard: 'July / 1969', fix: 'keep it together', at: 30, score: 640, sounds: [], repeated_ok: true }}
      />,
    )
    const card = screen.getByRole('note', { name: 'July 1969' })
    expect(card).toHaveTextContent('You paused between "July" and "1969". It\'s "July 1969" in one breath.')
    expect(card).toHaveTextContent('read right on the retry')
  })
})
