import { describe, expect, it } from 'vitest'
import { CONFIRM_INSTRUCTION, FINISH_INSTRUCTION, correctionInstruction, reviewInstruction } from './transport'

const verified = { kind: 'pronunciation' as const, word: 'verified', heard: 'b for v', fix: 'vɛrɪfaɪd', score: 41 }
const asLong = { kind: 'phrasing' as const, word: 'as long', heard: 'as / long', fix: 'keep it together', score: 0.9 }

describe('correctionInstruction', () => {
  it('tells the coach which word, what was heard, and to interrupt now', () => {
    expect(correctionInstruction(verified)).toBe(
      'Correction: the reader mispronounced "verified" (heard b for v). Interrupt now, two beats: "You said" the word as they said it, then "It\'s" the word right, then "Go on."',
    )
  })

  it('tells the coach which pair to keep together for a phrasing finding', () => {
    expect(correctionInstruction(asLong)).toBe(
      'Correction: the reader paused inside "as long" (as / long). Interrupt now, two beats: "You stopped after \'as\'", then "as long" as one piece, then "Go on."',
    )
  })
})

describe('reviewInstruction', () => {
  it('numbers every open finding and asks for them back', () => {
    expect(reviewInstruction([verified, asLong])).toBe(
      'Review: the reader has finished. Go through these in order, two beats each: what they said, then the right version. 1) "verified": heard b for v. 2) "as long": paused after "as". Then say: "Read those back to me." and wait.',
    )
  })

  it('is the plain closing when nothing is open', () => {
    expect(reviewInstruction([])).toBe(FINISH_INSTRUCTION)
  })
})

it('confirms in one word', () => {
  expect(CONFIRM_INSTRUCTION).toBe('Repeat OK: the reader repeated it right. Say "Good." and nothing else.')
})
