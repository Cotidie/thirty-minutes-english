import type { Shown } from './assessor/judge'

/** What is drawn on a paragraph's words: slashes, and the findings a reader can click. */
export interface Marks {
  /** Word indices a fluent reader starts a new thought group on: a slash goes before each. */
  breaks: number[]
  findings: Shown[]
  /** Index into `findings` of the one whose card is open. */
  open: number | null
  onOpen: (index: number) => void
}

/** Word index by the character offset of each word's first letter. Words are whitespace-separated, as the judge counts them. */
export function wordStarts(paragraph: string): Map<number, number> {
  const starts = new Map<number, number>()
  let index = 0
  for (const m of paragraph.matchAll(/\S+/g)) starts.set(m.index, index++)
  return starts
}

/** One word of a paragraph, or the whitespace between two. */
export interface Atom {
  text: string
  /** Where it starts in the paragraph. */
  offset: number
  /** The word's index in the paragraph; null for whitespace or a word cut by a sentence boundary. */
  word: number | null
}

/** `text`, which starts at `start` in the paragraph, cut into words and gaps. */
export function atoms(text: string, start: number, starts: Map<number, number>): Atom[] {
  const out: Atom[] = []
  let cursor = 0
  for (const m of text.matchAll(/\S+/g)) {
    if (m.index > cursor) out.push({ text: text.slice(cursor, m.index), offset: start + cursor, word: null })
    out.push({ text: m[0], offset: start + m.index, word: starts.get(start + m.index) ?? null })
    cursor = m.index + m[0].length
  }
  if (cursor < text.length) out.push({ text: text.slice(cursor), offset: start + cursor, word: null })
  return out
}
