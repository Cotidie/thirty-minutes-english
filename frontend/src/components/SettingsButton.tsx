import { useEffect, useState } from 'react'
import { SettingsModal } from './SettingsModal'
import './SettingsButton.css'

/** The gear in the corner of every page. `,` opens it, like most editors. */
export function SettingsButton() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (open || e.key !== ',' || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      e.preventDefault()
      setOpen(true)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <>
      <button
        type="button"
        className="settings-open"
        onClick={() => setOpen(true)}
        aria-label="Settings"
        aria-keyshortcuts=","
        title="Settings (,)"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm7.4-3.5a7.4 7.4 0 0 0-.1-1.2l2.1-1.6-2-3.5-2.5 1a7.6 7.6 0 0 0-2-1.2L14.5 3h-5l-.4 2.5a7.6 7.6 0 0 0-2 1.2l-2.5-1-2 3.5 2.1 1.6a7.4 7.4 0 0 0 0 2.4L2.6 14.8l2 3.5 2.5-1a7.6 7.6 0 0 0 2 1.2l.4 2.5h5l.4-2.5a7.6 7.6 0 0 0 2-1.2l2.5 1 2-3.5-2.1-1.6c.1-.4.1-.8.1-1.2Z"
          />
        </svg>
      </button>
      <SettingsModal open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}
