import './Synonyms.css'

/** Plainer words for the same meaning, one line under it; nothing on sessions made before synonyms. */
export function Synonyms({ words }: { words?: string[] }) {
  if (!words?.length) return null
  return (
    <span className="synonyms">
      <span className="synonyms-mark" aria-label="Similar:">≈</span> {words.join(', ')}
    </span>
  )
}
