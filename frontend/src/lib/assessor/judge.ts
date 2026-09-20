// Pure rules that turn one Azure-recognised segment into what the coach says.
// Azure scores every word of the paragraph the reader just said; this file
// decides which findings are worth a correction, and whether a repeat after a
// correction came out right. Two modes: `interrupt` corrects as the reader
// goes (one finding per segment, two tries per word); `after` only collects
// while they read and confirms repeats once `finish()` has been called.

export interface AzurePhoneme {
  Phoneme: string
  PronunciationAssessment: { AccuracyScore: number; NBestPhonemes?: { Phoneme: string; Score: number }[] }
}

export interface AzureWord {
  Word: string
  Offset: number
  Duration: number
  PronunciationAssessment: {
    AccuracyScore: number
    ErrorType: string
    Feedback?: {
      Prosody?: {
        Break?: { UnexpectedBreak?: { Confidence: number }; MissingBreak?: { Confidence: number }; BreakLength?: number }
      }
    }
  }
  Phonemes?: AzurePhoneme[]
}

export interface Thresholds {
  /** A word scored below this is a mispronunciation. */
  wordScore: number
  /** An unexpected-break confidence above this is a pause inside a phrase. */
  breakConfidence: number
}

export type FeedbackMode = 'interrupt' | 'after'

export interface Finding {
  kind: 'pronunciation' | 'phrasing'
  /** The word, or for phrasing the two words that stay together. */
  word: string
  /** What was heard: "b for v", or "as / long". */
  heard: string
  /** The few-word fix the coach relays. */
  fix: string
  score: number
}

export interface Verdict {
  /** New findings to act on: at most one in `interrupt` mode. */
  findings: Finding[]
  /** Earlier findings the reader has now repeated right. */
  confirmed: Finding[]
}

const MAX_TRIES = 2

/** Every finding in a segment, in reading order. */
export function findingsIn(words: AzureWord[], t: Thresholds): Finding[] {
  const found: Finding[] = []
  words.forEach((w, i) => {
    const pa = w.PronunciationAssessment
    if (pa.ErrorType === 'Omission' || pa.ErrorType === 'Insertion') return
    const breakConfidence = pa.Feedback?.Prosody?.Break?.UnexpectedBreak?.Confidence ?? 0
    if (i > 0 && breakConfidence > t.breakConfidence) {
      const prev = words[i - 1].Word
      found.push({ kind: 'phrasing', word: `${prev} ${w.Word}`, heard: `${prev} / ${w.Word}`, fix: 'keep it together', score: breakConfidence })
    }
    // Azure's own Mispronunciation tag sits at a fixed 60; the setting is the one knob here.
    if (pa.AccuracyScore < t.wordScore) {
      found.push({ kind: 'pronunciation', word: w.Word, heard: heardSound(w, t.wordScore), fix: expectedSound(w), score: pa.AccuracyScore })
    }
  })
  return found
}

/** "b for v": the most likely heard phoneme in place of the worst expected one. */
function heardSound(w: AzureWord, wordScore: number): string {
  const worst = [...(w.Phonemes ?? [])]
    .filter((p) => p.PronunciationAssessment.AccuracyScore < wordScore)
    .sort((a, b) => a.PronunciationAssessment.AccuracyScore - b.PronunciationAssessment.AccuracyScore)[0]
  if (!worst) return 'unclear'
  const heard = worst.PronunciationAssessment.NBestPhonemes?.find((n) => n.Phoneme !== worst.Phoneme)?.Phoneme
  return heard ? `${heard} for ${worst.Phoneme}` : `${worst.Phoneme} unclear`
}

function expectedSound(w: AzureWord): string {
  return (w.Phonemes ?? []).map((p) => p.Phoneme).join('')
}

/** Holds what has been corrected, so a later segment can confirm the repeat. */
export class Judge {
  private pending: Finding[] = []
  private tries = new Map<string, number>()
  /** In `after` mode, repeats only count once the reader has finished. */
  private listening: boolean
  private readonly t: Thresholds
  private readonly mode: FeedbackMode

  constructor(t: Thresholds, mode: FeedbackMode = 'interrupt') {
    this.t = t
    this.mode = mode
    this.listening = mode === 'interrupt'
  }

  segment(words: AzureWord[]): Verdict {
    const all = findingsIn(words, this.t)
    const confirmed = this.listening ? this.pending.filter((p) => repeatedRight(p, words, all)) : []
    this.pending = this.pending.filter((p) => !confirmed.includes(p))

    const fresh = all.filter((f) => (this.tries.get(f.word) ?? 0) < (this.mode === 'interrupt' ? MAX_TRIES : 1))
    const findings = this.mode === 'interrupt' ? fresh.slice(0, 1) : dedupe(fresh)
    for (const f of findings) {
      this.tries.set(f.word, (this.tries.get(f.word) ?? 0) + 1)
      this.pending = [...this.pending.filter((p) => p.word !== f.word), f]
    }
    return { findings, confirmed }
  }

  /** The reader is done: what is still uncorrected, in reading order. Repeats count from now on. */
  finish(): Finding[] {
    this.listening = true
    return [...this.pending]
  }
}

function dedupe(findings: Finding[]): Finding[] {
  const seen = new Set<string>()
  return findings.filter((f) => !seen.has(f.word) && seen.add(f.word))
}

function repeatedRight(pending: Finding, words: AzureWord[], findings: Finding[]): boolean {
  const said = words.map((w) => w.Word.toLowerCase())
  const target = pending.word.toLowerCase().split(' ')
  const present = target.every((t) => said.includes(t))
  const stillWrong = findings.some((f) => f.word === pending.word)
  return present && !stillWrong
}
