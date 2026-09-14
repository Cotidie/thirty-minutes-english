import type { SentencePair } from '../types'

export interface Piece {
  text: string
  /** Where the piece starts in its paragraph. */
  start: number
  /** The Korean for this sentence, or null for text the model did not pair. */
  ko: string | null
}

/**
 * Each paragraph cut into its translated sentences, in order. Pairs are
 * consumed front to back across paragraphs, so a short sentence that recurs
 * later lands on its own occurrence. Text between matches (spacing, or a
 * sentence with no pair) stays as a plain run.
 */
export function pairSentences(paragraphs: string[], pairs: SentencePair[]): Piece[][] {
  let next = 0
  return paragraphs.map((paragraph) => {
    const pieces: Piece[] = []
    let cursor = 0
    while (next < pairs.length) {
      const en = pairs[next].en.trim()
      const at = en ? paragraph.indexOf(en, cursor) : -1
      if (at < 0) break
      if (at > cursor) pieces.push({ text: paragraph.slice(cursor, at), start: cursor, ko: null })
      pieces.push({ text: en, start: at, ko: pairs[next].ko })
      cursor = at + en.length
      next += 1
    }
    if (cursor < paragraph.length || pieces.length === 0) {
      pieces.push({ text: paragraph.slice(cursor), start: cursor, ko: null })
    }
    return pieces
  })
}
