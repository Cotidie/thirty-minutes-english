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

/** One sound of a word as Azure scored it. */
export interface Sound {
  /** IPA, as the word should have it. */
  phoneme: string
  /** 0 to 100. */
  score: number
  /** Under the word threshold: this sound is what went wrong. */
  weak: boolean
  /** The IPA Azure heard instead, when weak and another sound fit better. */
  heard?: string
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
  /** Word accuracy, 0 to 100; for phrasing, how long the pause was in milliseconds. */
  score: number
  /** Every sound of the word in order. Empty for phrasing. */
  sounds: Sound[]
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
    const brk = pa.Feedback?.Prosody?.Break
    if (i > 0 && (brk?.UnexpectedBreak?.Confidence ?? 0) > t.breakConfidence) {
      const prev = words[i - 1].Word
      found.push({
        kind: 'phrasing',
        word: `${prev} ${w.Word}`,
        heard: `${prev} / ${w.Word}`,
        fix: 'keep it together',
        at: positions[i],
        score: Math.round((brk?.BreakLength ?? 0) / TICKS_PER_MS),
        sounds: [],
      })
    }
    // Azure's own Mispronunciation tag sits at a fixed 60; the setting is the one knob here.
    if (pa.AccuracyScore < t.wordScore) {
      const sounds = soundsOf(w, t.wordScore)
      found.push({
        kind: 'pronunciation',
        word: w.Word,
        heard: heardSound(sounds),
        fix: sounds.map((s) => s.phoneme).join(''),
        at: positions[i],
        score: Math.round(pa.AccuracyScore),
        sounds,
      })
    }
  })
  return found
}

/** Azure offsets and durations are in 100 ns ticks. */
const TICKS_PER_MS = 10_000

/** Each sound scored, with what was heard instead when it fell under the threshold. */
function soundsOf(w: AzureWord, wordScore: number): Sound[] {
  return (w.Phonemes ?? []).map((p) => {
    const score = Math.round(p.PronunciationAssessment.AccuracyScore)
    const weak = score < wordScore
    const other = weak ? p.PronunciationAssessment.NBestPhonemes?.find((n) => n.Phoneme !== p.Phoneme)?.Phoneme : undefined
    return other ? { phoneme: p.Phoneme, score, weak, heard: other } : { phoneme: p.Phoneme, score, weak }
  })
}

/** "b for v": the worst sound, with what was heard in its place. */
function heardSound(sounds: Sound[]): string {
  const worst = sounds.filter((s) => s.weak).sort((a, b) => a.score - b.score)[0]
  if (!worst) return 'unclear'
  return worst.heard ? `${worst.heard} for ${worst.phoneme}` : `${worst.phoneme} unclear`
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
  private readonly breaks: number[]
  private cursor = 0
  private readonly t: Thresholds

  /** `breaks`: word indices where a pause is expected, so none is a finding there. */
  constructor(t: Thresholds, paragraph: string, breaks: number[] = []) {
    this.t = t
    this.breaks = breaks
    this.raw = tokens(paragraph)
    this.words = this.raw.map(norm)
  }

  segment(words: AzureWord[]): Verdict {
    const all = findingsIn(words, this.t, this.locate(words))
      .filter((f) => f.kind !== 'phrasing' || !(this.punctuatedBefore(f.at) || this.breaks.includes(f.at)))
      .map((f) => this.spelled(f))
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

  /** The finding in the paragraph's own spelling (Azure lowercases): "July 1969", not "july 1969". */
  private spelled(f: Finding): Finding {
    if (f.at < 0) return f
    const w = this.word(f.at)
    if (f.kind === 'pronunciation') return { ...f, word: w }
    const prev = this.word(f.at - 1)
    return { ...f, word: `${prev} ${w}`, heard: `${prev} / ${w}` }
  }

  private word(at: number): string {
    return this.raw[at].replace(EDGE_PUNCTUATION, '')
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
const EDGE_PUNCTUATION = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu

function readRight(pending: Finding, words: AzureWord[], findings: Finding[]): boolean {
  const said = words.map((w) => norm(w.Word))
  const present = pending.word.split(' ').map(norm).every((t) => said.includes(t))
  const stillWrong = findings.some((f) => f.at === pending.at && f.kind === pending.kind)
  return present && !stillWrong
}
