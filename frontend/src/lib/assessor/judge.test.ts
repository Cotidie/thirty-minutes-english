import { describe, expect, it } from 'vitest'
import { findingsIn, Judge, type AzureWord } from './judge'

const T = { wordScore: 60, breakConfidence: 0.75 }

function word(
  text: string,
  score: number,
  extra: Partial<AzureWord['PronunciationAssessment']> = {},
  phonemes: AzureWord['Phonemes'] = [],
): AzureWord {
  return {
    Word: text,
    Offset: 0,
    Duration: 3_000_000,
    PronunciationAssessment: { AccuracyScore: score, ErrorType: score < 60 ? 'Mispronunciation' : 'None', ...extra },
    Phonemes: phonemes,
  }
}

const berified = word('verified', 41, {}, [
  { Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 8, NBestPhonemes: [{ Phoneme: 'b', Score: 80 }, { Phoneme: 'v', Score: 8 }] } },
  { Phoneme: 'ɛ', PronunciationAssessment: { AccuracyScore: 90 } },
  { Phoneme: 'r', PronunciationAssessment: { AccuracyScore: 88 } },
])

const brokenLong = word('long', 95, {
  Feedback: { Prosody: { Break: { UnexpectedBreak: { Confidence: 0.91 }, BreakLength: 6_000_000 } } },
})

describe('findingsIn', () => {
  it('reports a low word score as a pronunciation finding with the heard sound', () => {
    const [f] = findingsIn([word('researchers', 92), berified], T)
    expect(f).toEqual({ kind: 'pronunciation', word: 'verified', heard: 'b for v', fix: 'vɛr', score: 41 })
  })

  it('reports an unexpected break before a word as a phrasing finding on the pair', () => {
    const [f] = findingsIn([word('twice', 90), word('as', 88), brokenLong], T)
    expect(f).toEqual({ kind: 'phrasing', word: 'as long', heard: 'as / long', fix: 'keep it together', score: 0.91 })
  })

  it('ignores omissions, insertions, breaks under the threshold, and a break on the first word', () => {
    const skipped = [
      word('the', 0, { ErrorType: 'Omission' }),
      word('uh', 0, { ErrorType: 'Insertion' }),
      word('cold', 90, { Feedback: { Prosody: { Break: { UnexpectedBreak: { Confidence: 0.4 } } } } }),
    ]
    expect(findingsIn(skipped, T)).toEqual([])
    expect(findingsIn([brokenLong], T)).toEqual([])
  })

  it('respects the thresholds it is given', () => {
    expect(findingsIn([berified], { wordScore: 40, breakConfidence: 0.75 })).toEqual([])
    expect(findingsIn([word('as', 88), brokenLong], { wordScore: 60, breakConfidence: 0.95 })).toEqual([])
  })
})

describe('Judge in interrupt mode', () => {
  it('returns only the first finding of a segment', () => {
    const judge = new Judge(T)
    const { findings } = judge.segment([berified, word('as', 88), brokenLong])
    expect(findings.map((f) => f.word)).toEqual(['verified'])
  })

  it('confirms a repeat when the next segment carries the word clean, and stops after two tries', () => {
    const judge = new Judge(T)
    expect(judge.segment([berified]).findings[0].word).toBe('verified')
    const second = judge.segment([word('verified', 85)])
    expect(second.findings).toEqual([])
    expect(second.confirmed.map((f) => f.word)).toEqual(['verified'])

    expect(judge.segment([berified]).findings[0].word).toBe('verified')
    expect(judge.segment([berified])).toEqual({ findings: [], confirmed: [] })
  })

  it('confirms a phrasing repeat when the pair comes back without a break', () => {
    const judge = new Judge(T)
    judge.segment([word('as', 88), brokenLong])
    const { confirmed } = judge.segment([word('as', 90), word('long', 93)])
    expect(confirmed[0].word).toBe('as long')
  })
})

describe('Judge in after mode', () => {
  it('collects every finding, one per word, and does not confirm while the reader is still reading', () => {
    const judge = new Judge(T, 'after')
    const first = judge.segment([berified, word('as', 88), brokenLong])
    expect(first.findings.map((f) => f.word)).toEqual(['verified', 'as long'])
    const again = judge.segment([word('verified', 90), berified])
    expect(again).toEqual({ findings: [], confirmed: [] })
  })

  it('finish() lists what is still open, and repeats confirm from then on', () => {
    const judge = new Judge(T, 'after')
    judge.segment([berified, word('as', 88), brokenLong])
    expect(judge.finish().map((f) => f.word)).toEqual(['verified', 'as long'])
    const repeat = judge.segment([word('verified', 88)])
    expect(repeat.confirmed.map((f) => f.word)).toEqual(['verified'])
    expect(judge.finish().map((f) => f.word)).toEqual(['as long'])
  })
})
