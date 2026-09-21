import { describe, expect, it } from 'vitest'
import { correctionInstruction } from './transport'

const verified = { kind: 'pronunciation' as const, word: 'verified', heard: 'b for v', fix: 'vɛrɪfaɪd', at: 1, score: 41, sounds: [] }
const asLong = { kind: 'phrasing' as const, word: 'as long', heard: 'as / long', fix: 'keep it together', at: 4, score: 600, sounds: [] }

describe('correctionInstruction', () => {
  it('names the word and what was heard', () => {
    expect(correctionInstruction(verified)).toBe(
      'Correction: "verified", heard b for v.',
    )
  })

  it('names the pair and where the pause was', () => {
    expect(correctionInstruction(asLong)).toBe(
      'Correction: "as long", paused between "as" and "long".',
    )
  })
})
