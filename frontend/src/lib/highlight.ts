export interface Segment {
  text: string
  marked: boolean
}

export interface Span {
  start: number
  end: number
}

/** Where each evidence passage sits in the text, sorted by start. Case-insensitive. */
export function markedSpans(text: string, evidence: string[]): Span[] {
  const haystack = text.toLowerCase()
  const spans: Span[] = []
  for (const piece of evidence) {
    const needle = piece.trim().toLowerCase()
    if (!needle) continue
    const start = haystack.indexOf(needle)
    if (start >= 0) spans.push({ start, end: start + needle.length })
  }
  return spans.sort((a, b) => a.start - b.start)
}

/**
 * `text` cut into marked and plain runs. `spans` are in the coordinates of a
 * parent string in which `text` starts at `offset`, so one passage can be
 * marked across several pieces of the same paragraph.
 */
export function segmentsIn(text: string, spans: Span[], offset = 0): Segment[] {
  const segments: Segment[] = []
  let cursor = 0
  for (const span of spans) {
    const start = Math.max(span.start - offset, 0)
    const end = Math.min(span.end - offset, text.length)
    if (end <= start || start < cursor) continue
    if (start > cursor) segments.push({ text: text.slice(cursor, start), marked: false })
    segments.push({ text: text.slice(start, end), marked: true })
    cursor = end
  }
  if (cursor < text.length || segments.length === 0) segments.push({ text: text.slice(cursor), marked: false })
  return segments
}

export function highlightSegments(text: string, evidence: string[]): Segment[] {
  return segmentsIn(text, markedSpans(text, evidence))
}
