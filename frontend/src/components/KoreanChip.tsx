import { useState } from 'react'
import './KoreanChip.css'

/** A dashed blank pill; a tap turns it over to the Korean, another hides it again.
 * A button of its own, so it works inside a row whose parent has a click of its own. */
export function KoreanChip({ korean, of }: { korean: string; of: string }) {
  const [shown, setShown] = useState(false)
  return (
    <button
      type="button"
      className={`korean-chip${shown ? ' is-shown' : ''}`}
      aria-pressed={shown}
      aria-label={shown ? `Hide the Korean for ${of}` : `Korean for ${of}`}
      title={shown ? 'Hide' : 'Korean'}
      onClick={(e) => {
        e.stopPropagation()
        setShown((s) => !s)
      }}
    >
      {shown ? korean : '한'}
    </button>
  )
}
