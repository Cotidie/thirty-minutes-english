import './StarButton.css'
interface Props {
  label: string
  on: boolean
  onToggle: () => void
}

export function StarButton({ label, on, onToggle }: Props) {
  return (
    <button
      type="button"
      className={`star${on ? ' is-on' : ''}`}
      aria-pressed={on}
      aria-label={`Star ${label}`}
      title={on ? 'Remove from the summary' : 'Keep in the summary'}
      onClick={(e) => {
        e.stopPropagation()
        onToggle()
      }}
    >
      {on ? '★' : '☆'}
    </button>
  )
}
