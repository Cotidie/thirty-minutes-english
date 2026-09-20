import { describe, expect, it } from 'vitest'
import { CONFIRM_INSTRUCTION, FINISH_INSTRUCTION, correctionInstruction, reviewInstruction } from './transport'

const verified = { kind: 'pronunciation' as const, word: 'verified', heard: 'b for v', fix: 'vɛrɪfaɪd', score: 41, at: 1 }
const asLong = { kind: 'phrasing' as const, word: 'as long', heard: 'as / long', fix: 'keep it together', score: 0.9, at: 4 }

describe('correctionInstruction', () => {
  it('tells the coach which word, what was heard, and that the reader is asking', () => {
    expect(correctionInstruction(verified)).toBe(
      'Correction: the reader mispronounced "verified" (heard b for v) and is asking about it now. Two beats: "You said" the word as they said it, then "It\'s" the word right. Then "Try it."',
    )
  })

  it('tells the coach which pair to keep together for a phrasing finding', () => {
    expect(correctionInstruction(asLong)).toBe(
      'Correction: the reader paused inside "as long" (as / long) and is asking about it now. Two beats: "You stopped after \'as\'", then "as long" as one piece. Then "Try it."',
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
  expect(CONFIRM_INSTRUCTION).toBe('Repeat OK: the reader read it right this time. Say "Good." and nothing else.')
})
