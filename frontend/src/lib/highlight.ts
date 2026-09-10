export interface Segment {
  text: string
  marked: boolean
}

interface Span {
  start: number
  end: number
}

export function highlightSegments(text: string, evidence: string[]): Segment[] {
  const haystack = text.toLowerCase()
  const spans: Span[] = []
  for (const piece of evidence) {
    const needle = piece.trim().toLowerCase()
    if (!needle) continue
    const start = haystack.indexOf(needle)
    if (start >= 0) spans.push({ start, end: start + needle.length })
  }
  spans.sort((a, b) => a.start - b.start)

  const segments: Segment[] = []
  let cursor = 0
  for (const span of spans) {
    if (span.start < cursor) continue
    if (span.start > cursor) segments.push({ text: text.slice(cursor, span.start), marked: false })
    segments.push({ text: text.slice(span.start, span.end), marked: true })
    cursor = span.end
  }
  if (cursor < text.length || segments.length === 0) segments.push({ text: text.slice(cursor), marked: false })
  return segments
}
