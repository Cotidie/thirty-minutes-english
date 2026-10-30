import type { CSSProperties } from 'react'
import { personColor } from '../lib/presence/store'
import { useOthersOnTab } from '../lib/presence/useOthersOnTab'
import './TabPeople.css'

/** A dot in each person's color on the tab they are on. */
export function TabPeople({ tab }: { tab: number }) {
  const colors = useOthersOnTab(tab)
  if (colors.length === 0) return null
  return (
    <span className="tab-people">
      {colors.map((color) => (
        <span
          key={color}
          role="img"
          aria-label="Someone else is here"
          className="tab-person"
          style={{ '--person': personColor(color) } as CSSProperties}
        />
      ))}
    </span>
  )
}
