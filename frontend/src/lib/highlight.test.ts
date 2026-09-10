import { describe, expect, it } from 'vitest'
import { highlightSegments } from './highlight'

const text = 'The trouble starts the day after go-live. A real factory changes constantly.'

describe('highlightSegments', () => {
  it('returns one plain segment when nothing matches', () => {
    expect(highlightSegments(text, ['not in the text'])).toEqual([{ text, marked: false }])
  })

  it('marks an exact substring', () => {
    expect(highlightSegments(text, ['A real factory changes constantly.'])).toEqual([
      { text: 'The trouble starts the day after go-live. ', marked: false },
      { text: 'A real factory changes constantly.', marked: true },
    ])
  })

  it('matches case-insensitively and keeps the original casing', () => {
    const segments = highlightSegments(text, ['the trouble starts'])
    expect(segments[0]).toEqual({ text: 'The trouble starts', marked: true })
  })

  it('marks several pieces in text order and skips overlaps', () => {
    const segments = highlightSegments(text, ['changes constantly', 'trouble starts', 'starts the day'])
    expect(segments.filter((s) => s.marked).map((s) => s.text)).toEqual(['trouble starts', 'changes constantly'])
  })
})
