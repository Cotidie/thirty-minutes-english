import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FindingCard } from './FindingCard'

describe('FindingCard', () => {
  it('lays out the word sound by sound, what was heard, and how to make each missed sound', () => {
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
    expect(card).toHaveTextContent('/ænsɚd/')
    expect(card).toHaveTextContent('42 / 100')
    expect([...card.querySelectorAll('dd')].map((row) => row.textContent)).toEqual(['ænsɚd', 'ɪns?d'])
    expect([...card.querySelectorAll('dd .is-weak')].map((s) => s.textContent)).toEqual(['æ', 'ɚ', 'ɪ', '?'])
    const tips = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(tips[0]).toBe('æ as in cAt: you said ɪ as in sIt. Jaw drops, mouth wide, tongue low and front. Longer than "e".')
    expect(tips[1]).toBe('ɚ as in lettER came out unclear. Weak vowel with the tongue curled back for r.')
  })

  it('explains a pause inside a phrase with its length, and notes a retry that came out right', () => {
    render(
      <FindingCard
        finding={{ kind: 'phrasing', word: 'July 1969', heard: 'July / 1969', fix: 'keep it together', at: 30, score: 640, sounds: [], repeated_ok: true }}
      />,
    )
    const card = screen.getByRole('note', { name: 'July 1969' })
    expect(card).toHaveTextContent('paused 0.6 s')
    expect(card).toHaveTextContent('You paused between "July" and "1969". They belong to one thought group: read "July 1969" in one breath')
    expect(card).toHaveTextContent('read right on the retry')
  })
})
