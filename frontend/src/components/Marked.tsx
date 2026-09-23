import { phrasePattern } from '../lib/phraseMatch'
import './Marked.css'

/** `text` with the word or expression marked wherever it is used, in whatever form it takes there. */
export function Marked({ text, word }: { text: string; word: string }) {
  const found = phrasePattern(word, text)
  if (!found) return <>{text}</>
  const parts = text.split(found)
  return <>{parts.map((part, i) => (i % 2 ? <mark key={i} className="marked">{part}</mark> : part))}</>
}
