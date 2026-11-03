import { useEffect, type RefObject } from 'react'

/** How a panel was left: by Escape, where focus should go back to its button, or by a press elsewhere, which moves it. */
export type Leaving = 'escape' | 'outside'

/** While `open`, Escape or a press outside `here` calls `close`: how a panel that drops from a corner button goes away. */
export function useCloseOnLeave(open: boolean, here: RefObject<HTMLElement | null>, close: (how: Leaving) => void): void {
  useEffect(() => {
    if (!open) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close('escape')
    }
    const closeOutside = (event: PointerEvent) => {
      if (!here.current?.contains(event.target as Node)) close('outside')
    }
    document.addEventListener('keydown', closeOnEscape)
    document.addEventListener('pointerdown', closeOutside)
    return () => {
      document.removeEventListener('keydown', closeOnEscape)
      document.removeEventListener('pointerdown', closeOutside)
    }
  }, [open, here, close])
}
