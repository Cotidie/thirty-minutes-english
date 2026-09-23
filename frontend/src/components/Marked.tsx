import './Marked.css'

/** `text` with `word` marked wherever it appears, in whatever form it takes there (retract → retracted). */
export function Marked({ text, word }: { text: string; word: string }) {
  const stem = word.replace(/e$/, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = text.split(new RegExp(`(\\b${stem}\\w*)`, 'i'))
  return <>{parts.map((part, i) => (i % 2 ? <mark key={i} className="marked">{part}</mark> : part))}</>
}
