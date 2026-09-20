// Pure rules that turn one Azure-recognised segment into findings on the
// paragraph. Azure scores every word the reader just said; this file decides
// which are worth showing, where in the paragraph they sit, and whether a
// later read of the same word came out right. Nothing here speaks: the reader
// asks for a correction by clicking a finding.

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

export interface Finding {
  kind: 'pronunciation' | 'phrasing'
  /** The word, or for phrasing the two words that stay together. */
  word: string
  /** What was heard: "b for v", or "as / long". */
  heard: string
  /** The few-word fix the coach relays. */
  fix: string
  /** Index of the word in the paragraph; for phrasing, of the second word (the pause sits before it). -1 when unplaced. */
  at: number
}

export interface Verdict {
  /** New findings, one per paragraph position. */
  findings: Finding[]
  /** Earlier findings the reader has now read right. */
  confirmed: Finding[]
}

/** Every finding in a segment, in reading order, with `at` from `positions` (one per word). */
export function findingsIn(words: AzureWord[], t: Thresholds, positions: number[] = words.map(() => -1)): Finding[] {
  const found: Finding[] = []
  words.forEach((w, i) => {
    const pa = w.PronunciationAssessment
    if (pa.ErrorType === 'Omission' || pa.ErrorType === 'Insertion') return
    const breakConfidence = pa.Feedback?.Prosody?.Break?.UnexpectedBreak?.Confidence ?? 0
    if (i > 0 && breakConfidence > t.breakConfidence) {
      const prev = words[i - 1].Word
      found.push({ kind: 'phrasing', word: `${prev} ${w.Word}`, heard: `${prev} / ${w.Word}`, fix: 'keep it together', at: positions[i] })
    }
    // Azure's own Mispronunciation tag sits at a fixed 60; the setting is the one knob here.
    if (pa.AccuracyScore < t.wordScore) {
      found.push({ kind: 'pronunciation', word: w.Word, heard: heardSound(w, t.wordScore), fix: expectedSound(w), at: positions[i] })
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

/** The paragraph split on whitespace, punctuation kept for display. */
export const tokens = (paragraph: string): string[] => paragraph.split(/\s+/).filter(Boolean)

const norm = (word: string) => word.toLowerCase().replace(/[^\p{L}\p{N}']/gu, '')

/**
 * Collects findings while the reader goes, placed on the paragraph, and
 * confirms one when a later segment carries its words clean.
 */
export class Judge {
  private open: Finding[] = []
  private readonly words: string[]
  private readonly raw: string[]
  private cursor = 0
  private readonly t: Thresholds

  constructor(t: Thresholds, paragraph: string) {
    this.t = t
    this.raw = tokens(paragraph)
    this.words = this.raw.map(norm)
  }

  segment(words: AzureWord[]): Verdict {
    const all = findingsIn(words, this.t, this.locate(words)).filter((f) => f.kind !== 'phrasing' || !this.punctuatedBefore(f.at))
    const confirmed = this.open.filter((p) => readRight(p, words, all))
    this.open = this.open.filter((p) => !confirmed.includes(p))
    const findings = all.filter((f) => !this.open.some((p) => p.at === f.at && p.kind === f.kind))
    this.open = [...this.open, ...findings]
    return { findings, confirmed }
  }

  /**
   * Paragraph index of each said word. A short segment that matches an open
   * finding is the reader trying that word again, so it lands on the finding;
   * otherwise words are found forward from the last match, or from the top
   * when the reader went back.
   */
  private locate(words: AzureWord[]): number[] {
    const retry = words.length <= RETRY_WORDS
    return words.map((w) => {
      const target = norm(w.Word)
      const again = retry ? this.openPosition(target) : -1
      if (again >= 0) return again
      let i = this.words.indexOf(target, this.cursor)
      if (i < 0) i = this.words.indexOf(target)
      if (i >= 0) this.cursor = i + 1
      return i
    })
  }

  /** A pause after a period or comma is the reader's to take. */
  private punctuatedBefore(at: number): boolean {
    return at > 0 && PUNCTUATED.test(this.raw[at - 1])
  }

  private openPosition(target: string): number {
    for (const p of this.open) {
      const parts = p.word.split(' ').map(norm)
      const k = parts.indexOf(target)
      if (k >= 0) return p.at - (parts.length - 1 - k)
    }
    return -1
  }
}

/** A segment this short after a finding is a retry, not more of the paragraph. */
const RETRY_WORDS = 3
const PUNCTUATED = /[.,;:!?…"”')\]]$/

function readRight(pending: Finding, words: AzureWord[], findings: Finding[]): boolean {
  const said = words.map((w) => norm(w.Word))
  const present = pending.word.split(' ').map(norm).every((t) => said.includes(t))
  const stillWrong = findings.some((f) => f.at === pending.at && f.kind === pending.kind)
  return present && !stillWrong
}
