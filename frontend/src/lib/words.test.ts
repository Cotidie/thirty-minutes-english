import { describe, expect, it } from 'vitest'
import { atoms, wordStarts } from './words'

describe('wordStarts', () => {
  it('numbers words by the offset of their first letter', () => {
    expect([...wordStarts('Ambition is  cheap.')]).toEqual([
      [0, 0],
      [9, 1],
      [13, 2],
    ])
  })
})

describe('atoms', () => {
  const starts = wordStarts('Ambition is cheap. Upkeep pays.')

  it('cuts a sentence into words and gaps, each word carrying its paragraph index', () => {
    expect(atoms('Upkeep pays.', 19, starts)).toEqual([
      { text: 'Upkeep', word: 3 },
      { text: ' ', word: null },
      { text: 'pays.', word: 4 },
    ])
  })

  it('keeps the gap between sentences, and leaves a cut word unnumbered', () => {
    expect(atoms(' ', 18, starts)).toEqual([{ text: ' ', word: null }])
    expect(atoms('keep pays.', 21, starts)).toEqual([
      { text: 'keep', word: null },
      { text: ' ', word: null },
      { text: 'pays.', word: 4 },
    ])
  })
})
