import { describe, expect, it } from 'vitest'
import { correctionInstruction } from './transport'

const verified = { word: 'verified', heard: 'b for v', fix: 'vɛrɪfaɪd', at: 1, score: 41, sounds: [] }

describe('correctionInstruction', () => {
  it('names the word and what was heard', () => {
    expect(correctionInstruction(verified)).toBe(
      'Correction: "verified", heard b for v.',
    )
  })
})
