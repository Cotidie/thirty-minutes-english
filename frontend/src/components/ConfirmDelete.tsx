import { useState, type ReactNode } from 'react'

interface Props {
  /** What the row is called, for the button's name: "Delete <label>". */
  label: string
  /** What else goes with it, said while asking. */
  warning?: ReactNode
  /** Deletes it; the caller drops the row when this resolves, and the row stays with the error when it rejects. */
  onDelete: () => Promise<void>
}

/** A Delete button that asks once before it deletes. */
export function ConfirmDelete({ label, warning, onDelete }: Props) {
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await onDelete()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  if (!asking) {
    return (
      <button type="button" className="btn-link db-delete" aria-label={`Delete ${label}`} onClick={() => setAsking(true)}>
        Delete
      </button>
    )
  }
  return (
    <div className="db-confirm">
      {warning && <span>{warning}</span>}
      <button type="button" className="btn db-confirm-delete" disabled={busy} onClick={() => void remove()}>
        Delete for good
      </button>
      <button
        type="button"
        className="btn-link"
        onClick={() => {
          setAsking(false)
          setError(null)
        }}
      >
        Cancel
      </button>
      {error && <span className="error">Could not delete it: {error}</span>}
    </div>
  )
}
