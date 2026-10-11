// Pure rules that turn one Azure-recognised segment into findings on the
// paragraph. Azure scores every word the reader just said; this file decides
// which are worth showing, where in the paragraph they sit, and whether a
// later read of the same word came out right. Nothing here speaks: the reader
// asks for a correction by clicking a finding.

interface AzurePhoneme {
  Phoneme: string
  PronunciationAssessment: { AccuracyScore: number; NBestPhonemes?: { Phoneme: string; Score: number }[] }
}

export interface AzureWord {
  Word: string
  PronunciationAssessment: { AccuracyScore: number; ErrorType: string }
  Phonemes?: AzurePhoneme[]
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

/** A word scored below the threshold: a mispronunciation. */
export interface Finding {
  word: string
  /** What was heard: "b for v". */
  heard: string
  /** The word in IPA, as it should sound. */
  fix: string
  /** Index of the word in the paragraph. -1 when unplaced. */
  at: number
  /** Word accuracy, 0 to 100. */
  score: number
  /** Every sound of the word in order. */
  sounds: Sound[]
}

/** A finding as the page shows it. */
export interface Shown extends Finding {
  /** The reader has since read it right. */
  repeated_ok: boolean
}

export interface Verdict {
  /** New findings, one per paragraph position. */
  findings: Finding[]
  /** Earlier findings the reader has now read right. */
  confirmed: Finding[]
}

/**
 * Every finding in a segment, in reading order, with `at` from `positions` (one per word).
 * Azure's own Mispronunciation tag sits at a fixed 60; `wordScore` is the one knob here.
 */
export function findingsIn(words: AzureWord[], wordScore: number, positions: number[] = words.map(() => -1)): Finding[] {
  return words.flatMap((w, i) => {
    const pa = w.PronunciationAssessment
    if (pa.ErrorType === 'Omission' || pa.ErrorType === 'Insertion' || pa.AccuracyScore >= wordScore) return []
    const sounds = soundsOf(w, wordScore)
    return [
      {
        word: w.Word,
        heard: heardSound(sounds),
        fix: sounds.map((s) => s.phoneme).join(''),
        at: positions[i],
        score: Math.round(pa.AccuracyScore),
        sounds,
      },
    ]
  })
}

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
const tokens = (paragraph: string): string[] => paragraph.split(/\s+/).filter(Boolean)

const norm = (word: string) => word.toLowerCase().replace(/[^\p{L}\p{N}']/gu, '')

/**
 * Collects findings while the reader goes, placed on the paragraph, and
 * confirms one when a later segment carries its word clean.
 */
export class Judge {
  private open: Finding[] = []
  private readonly words: string[]
  private readonly raw: string[]
  private cursor = 0
  private readonly wordScore: number

  /** `wordScore`: a word scored below this is a mispronunciation. */
  constructor(wordScore: number, paragraph: string) {
    this.wordScore = wordScore
    this.raw = tokens(paragraph)
    this.words = this.raw.map(norm)
  }

  segment(words: AzureWord[]): Verdict {
    const all = findingsIn(words, this.wordScore, this.locate(words)).map((f) => this.spelled(f))
    const said = words.map((w) => norm(w.Word))
    const confirmed = this.open.filter((p) => said.includes(norm(p.word)) && !all.some((f) => f.at === p.at))
    this.open = this.open.filter((p) => !confirmed.includes(p))
    const findings = all.filter((f) => !this.open.some((p) => p.at === f.at))
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
      const again = retry ? this.open.find((p) => norm(p.word) === target) : undefined
      if (again) return again.at
      let i = this.words.indexOf(target, this.cursor)
      if (i < 0) i = this.words.indexOf(target)
      if (i >= 0) this.cursor = i + 1
      return i
    })
  }

  /** The finding in the paragraph's own spelling (Azure lowercases): "Verified", not "verified". */
  private spelled(f: Finding): Finding {
    return f.at < 0 ? f : { ...f, word: this.raw[f.at].replace(EDGE_PUNCTUATION, '') }
  }
}

/** A segment this short after a finding is a retry, not more of the paragraph. */
const RETRY_WORDS = 3
const EDGE_PUNCTUATION = /^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu
