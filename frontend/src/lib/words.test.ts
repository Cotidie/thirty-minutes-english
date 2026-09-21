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
      { text: 'Upkeep', offset: 19, word: 3 },
      { text: ' ', offset: 25, word: null },
      { text: 'pays.', offset: 26, word: 4 },
    ])
  })

  it('keeps the gap between sentences, and leaves a cut word unnumbered', () => {
    expect(atoms(' ', 18, starts)).toEqual([{ text: ' ', offset: 18, word: null }])
    expect(atoms('keep pays.', 21, starts)).toEqual([
      { text: 'keep', offset: 21, word: null },
      { text: ' ', offset: 25, word: null },
      { text: 'pays.', offset: 26, word: 4 },
    ])
  })
})
