import { useState } from 'react'
import type { SettingOption } from '../types'
import { PinIcon } from './Choice'
import './ModelList.css'

/** Each sort's order (stable, so ties keep the provider's newest-first) and whether a model has its figure. */
const SORTS = {
  newest: { label: 'Newest', key: () => 0, has: () => true },
  /** What a picture cost here, else the list price; unpriced models last. */
  cheapest: {
    label: 'Cheapest',
    key: (o: SettingOption) => o.per_image ?? (o.image_per_m != null ? o.image_per_m / 1000 : Infinity),
    has: (o: SettingOption) => o.per_image != null || o.image_per_m != null,
  },
  fastest: {
    label: 'Fastest',
    key: (o: SettingOption) => o.seconds_per_image ?? Infinity,
    has: (o: SettingOption) => o.seconds_per_image != null,
  },
}
type Sort = keyof typeof SORTS

function dollars(n: number): string {
  if (n === 0) return 'free'
  if (n >= 10) return `$${n.toFixed(0)}`
  return `$${n.toFixed(n >= 0.1 ? 2 : 3)}`
}

/** What a picture cost and took here, when we drew with the model; the provider's list price beside it. */
export function priceOf(option: SettingOption): { perPicture: string; list: string } {
  const here = [
    option.per_image != null ? dollars(option.per_image) : '',
    option.seconds_per_image != null ? `${Math.round(option.seconds_per_image)}s` : '',
  ].filter(Boolean)
  return {
    perPicture: here.length ? `≈ ${here.join(' · ')} / picture` : 'no picture yet',
    list: option.image_per_m != null ? `${dollars(option.image_per_m)} / 1M tok` : '',
  }
}

interface Props {
  name: string
  labelledBy: string
  options: SettingOption[]
  /** The saved model id; blank means the default. */
  value: string
  default: string
  onChange: (value: string) => void
  onPin: (model: string, pinned: boolean) => void
}

/**
 * An image model picked from a list in the panel: pinned models first, then the provider's
 * newest (or cheapest, or fastest), each with what a picture cost and took here and the list
 * price. A model the provider does not list goes in the id field under the list.
 */
export function ModelList({ name, labelledBy, options, value, default: fallback, onChange, onPin }: Props) {
  // A column or a sort shows only when some model has its figure: comfy has no list prices.
  const listed = options.some((o) => o.image_per_m != null)
  const measured = options.some((o) => o.per_image != null || o.seconds_per_image != null)
  const sorts = (Object.keys(SORTS) as Sort[]).filter((s) => options.some(SORTS[s].has))
  const [picked, setSort] = useState<Sort>('newest')
  const sort = sorts.includes(picked) ? picked : 'newest'
  const columns = listed ? '' : measured ? ' no-list' : ' no-figures'
  const [filter, setFilter] = useState('')
  const chosen = value || fallback
  const needle = filter.trim().toLowerCase()
  const matching = options.filter((o) => !needle || `${o.id} ${o.label}`.toLowerCase().includes(needle))
  const key = SORTS[sort].key
  const ordered = [...matching].sort((a, b) => (key(a) === key(b) ? 0 : key(a) < key(b) ? -1 : 1)) // Infinity - Infinity is NaN
  const sections = [
    { title: 'Pinned', rows: ordered.filter((o) => o.pinned) },
    { title: SORTS[sort].label, rows: ordered.filter((o) => !o.pinned) },
  ].filter((s) => s.rows.length > 0)
  const known = options.some((o) => o.id === value)

  return (
    <div className="model-list">
      <div className="model-list-bar">
        <input
          type="search"
          aria-label="Filter models"
          placeholder={`Filter ${options.length} models`}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {sorts.length > 1 && (
          <div className="model-list-sort" role="group" aria-label="Sort models">
            {sorts.map((s) => (
              <button key={s} type="button" aria-pressed={sort === s} onClick={() => setSort(s)}>
                {SORTS[s].label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className={`model-list-rows${columns}`} role="radiogroup" aria-labelledby={labelledBy}>
        {sections.map((section) => (
          <div key={section.title} className="model-list-section">
            <p className="model-list-head">{section.title}</p>
            {section.rows.map((o) => {
              const price = priceOf(o)
              return (
                <div key={o.id} className={`model-list-row${o.id === chosen ? ' is-chosen' : ''}`}>
                  <label className="model-list-pick" title={o.id}>
                    <input type="radio" name={name} checked={o.id === chosen} onChange={() => onChange(o.id)} />
                    <span className="model-list-name">{o.label || o.id}</span>
                  </label>
                  {(listed || measured) && (
                    <span className={`model-list-cost${price.perPicture.startsWith('≈') ? ' is-measured' : ''}`}>{price.perPicture}</span>
                  )}
                  {listed && <span className="model-list-price">{price.list}</span>}
                  <button
                    type="button"
                    className={`model-list-pin${o.pinned ? ' is-on' : ''}`}
                    aria-pressed={!!o.pinned}
                    aria-label={`${o.pinned ? 'Unpin' : 'Pin'} ${o.label || o.id}`}
                    title={o.pinned ? 'Unpin' : 'Pin: keep it at the top'}
                    onClick={() => onPin(o.id, !o.pinned)}
                  >
                    <PinIcon filled={!!o.pinned} />
                  </button>
                </div>
              )
            })}
          </div>
        ))}
        {sections.length === 0 && <p className="model-list-empty">No model matches “{filter}”.</p>}
      </div>
      <label className="model-list-other">
        <span>Other model id</span>
        <input
          type="text"
          autoComplete="off"
          placeholder="Not in the list? Type its id"
          value={known ? '' : value}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    </div>
  )
}
