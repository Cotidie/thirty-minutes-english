// PROTOTYPE, throwaway. Cycles `?variant=` with the arrows or ← →.
import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

interface Props {
  variants: { key: string; name: string }[]
  current: string
}

export function PrototypeSwitcher({ variants, current }: Props) {
  const navigate = useNavigate()
  const { hash } = useLocation()
  const index = variants.findIndex((v) => v.key === current)

  const go = (step: number) => {
    const next = variants[(index + step + variants.length) % variants.length]
    navigate({ search: `?variant=${next.key}`, hash }, { replace: true })
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target
      if (t instanceof HTMLElement && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName))) return
      if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'ArrowRight') go(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="np-switcher" role="toolbar" aria-label="Prototype variants">
      <button type="button" onClick={() => go(-1)} aria-label="Previous variant">
        ‹
      </button>
      <span>
        {current}: {variants[index].name}
      </span>
      <button type="button" onClick={() => go(1)} aria-label="Next variant">
        ›
      </button>
    </div>
  )
}
