import { describe, expect, it } from 'vitest'
import { CONFIRM_INSTRUCTION, correctionInstruction } from './transport'

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

it('confirms in one word', () => {
  expect(CONFIRM_INSTRUCTION).toBe('Repeat OK: the reader read it right this time. Say "Good." and nothing else.')
})
