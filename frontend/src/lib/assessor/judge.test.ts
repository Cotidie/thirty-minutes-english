import { describe, expect, it } from 'vitest'
import { findingsIn, Judge, type AzureWord } from './judge'

const WORD_SCORE = 60

function word(text: string, score: number, errorType = score < 60 ? 'Mispronunciation' : 'None', phonemes: AzureWord['Phonemes'] = []): AzureWord {
  return { Word: text, PronunciationAssessment: { AccuracyScore: score, ErrorType: errorType }, Phonemes: phonemes }
}

const berified = word('verified', 41, 'Mispronunciation', [
  { Phoneme: 'v', PronunciationAssessment: { AccuracyScore: 8, NBestPhonemes: [{ Phoneme: 'b', Score: 80 }, { Phoneme: 'v', Score: 8 }] } },
  { Phoneme: 'ɛ', PronunciationAssessment: { AccuracyScore: 90 } },
  { Phoneme: 'r', PronunciationAssessment: { AccuracyScore: 88 } },
])

describe('findingsIn', () => {
  it('reports a low word score as a finding with the heard sound', () => {
    const [f] = findingsIn([word('researchers', 92), berified], WORD_SCORE)
    expect(f).toEqual({
      word: 'verified',
      heard: 'b for v',
      fix: 'vɛr',
      at: -1,
      score: 41,
      sounds: [
        { phoneme: 'v', score: 8, weak: true, heard: 'b' },
        { phoneme: 'ɛ', score: 90, weak: false },
        { phoneme: 'r', score: 88, weak: false },
      ],
    })
  })

  it('calls a weak sound with no better fit unclear', () => {
    const muffled = word('think', 30, 'Mispronunciation', [{ Phoneme: 'θ', PronunciationAssessment: { AccuracyScore: 20 } }])
    const [f] = findingsIn([muffled], WORD_SCORE)
    expect(f.heard).toBe('θ unclear')
    expect(f.sounds).toEqual([{ phoneme: 'θ', score: 20, weak: true }])
    expect(findingsIn([word('think', 30)], WORD_SCORE)[0].heard).toBe('unclear')
  })

  it('ignores omissions and insertions, and respects the threshold it is given', () => {
    expect(findingsIn([word('the', 0, 'Omission'), word('uh', 0, 'Insertion')], WORD_SCORE)).toEqual([])
    expect(findingsIn([berified], 40)).toEqual([])
  })
})

const PARAGRAPH = 'Researchers verified it twice, as long as it held. They verified it again.'

it('spells a finding the way the paragraph does', () => {
  const judge = new Judge(WORD_SCORE, 'In July 1969, a landing. "Verified" it.')
  const { findings } = judge.segment([word('in', 90), word('july', 90), word('1969', 92), word('a', 90), word('landing', 90), berified])
  expect(findings.map((f) => [f.word, f.heard])).toEqual([['Verified', 'b for v']])
})

describe('Judge', () => {
  it('places a finding on the paragraph, one per position', () => {
    const judge = new Judge(WORD_SCORE, PARAGRAPH)
    const { findings } = judge.segment([word('researchers', 90), berified, word('it', 90), word('twice', 88)])
    expect(findings.map((f) => [f.word, f.at])).toEqual([['verified', 1]])
    expect(judge.segment([berified]).findings).toEqual([])
  })

  it('places the same word said later at its next occurrence, but a short retry on the open finding', () => {
    const judge = new Judge(WORD_SCORE, PARAGRAPH)
    judge.segment([word('as', 88), word('it', 90), word('held', 90)])
    expect(judge.segment([word('they', 90), berified]).findings[0].at).toBe(10)
    expect(judge.segment([berified]).findings).toEqual([])
    expect(judge.segment([word('researchers', 90), berified, word('it', 90), word('twice', 90)]).findings[0].at).toBe(1)
  })

  it('confirms a finding when a later segment carries the word clean', () => {
    const judge = new Judge(WORD_SCORE, PARAGRAPH)
    judge.segment([berified, word('it', 90), word('twice', 88)])
    const repeat = judge.segment([word('verified', 85)])
    expect(repeat.findings).toEqual([])
    expect(repeat.confirmed.map((f) => f.word)).toEqual(['verified'])
  })

  it('does not confirm a repeat that is still wrong', () => {
    const judge = new Judge(WORD_SCORE, PARAGRAPH)
    judge.segment([berified])
    expect(judge.segment([berified])).toEqual({ findings: [], confirmed: [] })
    expect(judge.segment([word('verified', 90)]).confirmed).toHaveLength(1)
  })
})
