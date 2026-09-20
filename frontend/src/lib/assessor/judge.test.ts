import { describe, expect, it } from 'vitest'
import { findingsIn, Judge, tokens, type AzureWord } from './judge'

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
    expect(f).toEqual({ kind: 'pronunciation', word: 'verified', heard: 'b for v', fix: 'vɛr', at: -1 })
  })

  it('reports an unexpected break before a word as a phrasing finding on the pair', () => {
    const [f] = findingsIn([word('twice', 90), word('as', 88), brokenLong], T, [0, 1, 2])
    expect(f).toEqual({ kind: 'phrasing', word: 'as long', heard: 'as / long', fix: 'keep it together', at: 2 })
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

it('tokens keeps punctuation on the word for display', () => {
  expect(tokens('Twice as long,\n"verified" it.')).toEqual(['Twice', 'as', 'long,', '"verified"', 'it.'])
})

const PARAGRAPH = 'Researchers verified it twice, as long as it held. They verified it again.'

it('spells a finding the way the paragraph does', () => {
  const judge = new Judge(T, 'In July 1969, a landing. "Verified" it.')
  const { findings } = judge.segment([word('in', 90), word('july', 90), word('1969', 92, brokenLong.PronunciationAssessment), word('a', 90), word('landing', 90), berified])
  expect(findings.map((f) => [f.word, f.heard])).toEqual([
    ['July 1969', 'July / 1969'],
    ['Verified', 'b for v'],
  ])
})

describe('Judge', () => {
  it('places every finding on the paragraph, one per position', () => {
    const judge = new Judge(T, PARAGRAPH)
    const { findings } = judge.segment([word('researchers', 90), berified, word('it', 90), word('twice', 88), word('as', 88), brokenLong])
    expect(findings.map((f) => [f.word, f.at])).toEqual([
      ['verified', 1],
      ['as long', 5],
    ])
    expect(judge.segment([berified]).findings).toEqual([])
  })

  it('places the same word said later at its next occurrence, but a short retry on the open finding', () => {
    const judge = new Judge(T, PARAGRAPH)
    judge.segment([word('as', 88), word('it', 90), word('held', 90)])
    expect(judge.segment([word('they', 90), berified]).findings[0].at).toBe(10)
    expect(judge.segment([berified]).findings).toEqual([])
    expect(judge.segment([word('researchers', 90), berified, word('it', 90), word('twice', 90)]).findings[0].at).toBe(1)
  })

  it('confirms a finding when a later segment carries the word clean, and keeps the rest pending', () => {
    const judge = new Judge(T, PARAGRAPH)
    judge.segment([berified, word('it', 90), word('twice', 88), word('as', 88), brokenLong])
    const repeat = judge.segment([word('verified', 85)])
    expect(repeat.findings).toEqual([])
    expect(repeat.confirmed.map((f) => f.word)).toEqual(['verified'])
    expect(judge.segment([word('as', 90), word('long', 93)]).confirmed.map((f) => f.word)).toEqual(['as long'])
  })

  it('lets a pause stand after a period or comma', () => {
    const judge = new Judge(T, 'They verified it. Twice, as long as it held.')
    const { findings } = judge.segment([word('it', 90), word('twice', 88, brokenLong.PronunciationAssessment), word('as', 88, brokenLong.PronunciationAssessment), brokenLong])
    expect(findings.map((f) => f.word)).toEqual(['as long'])
  })

  it('confirms a phrasing finding when the pair comes back without a break', () => {
    const judge = new Judge(T, PARAGRAPH)
    judge.segment([word('as', 88), brokenLong])
    const { confirmed } = judge.segment([word('as', 90), word('long', 93)])
    expect(confirmed[0].word).toBe('as long')
  })

  it('does not confirm a repeat that is still wrong', () => {
    const judge = new Judge(T, PARAGRAPH)
    judge.segment([berified])
    expect(judge.segment([berified])).toEqual({ findings: [], confirmed: [] })
    expect(judge.segment([word('verified', 90)]).confirmed).toHaveLength(1)
  })
})
