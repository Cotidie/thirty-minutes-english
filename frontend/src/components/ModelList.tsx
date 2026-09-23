import { useState } from 'react'
import type { SettingOption } from '../types'
import { PinIcon } from './Choice'
import './ModelList.css'

type Sort = 'newest' | 'cheapest'

function dollars(n: number): string {
  if (n === 0) return 'free'
  if (n >= 10) return `$${n.toFixed(0)}`
  return `$${n.toFixed(n >= 0.1 ? 2 : 3)}`
}

/** What a picture cost here, when we drew with the model; the provider's list price otherwise. */
export function priceOf(option: SettingOption): { perPicture: string; list: string } {
  const count = option.per_image_count ?? 0
  return {
    perPicture: option.per_image != null ? `≈ ${dollars(option.per_image)} / picture · ${count} drawn` : 'no picture yet',
    list: option.image_per_m != null ? `${dollars(option.image_per_m)} / 1M tok` : '',
  }
}

/** Cheapest first: what a picture cost here, else the list price; unpriced models last. */
function cost(o: SettingOption): number {
  return o.per_image ?? (o.image_per_m != null ? o.image_per_m / 1000 : Infinity)
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
 * newest (or cheapest), each with what a picture cost here and the list price. A model the
 * provider does not list goes in the id field under the list.
 */
export function ModelList({ name, labelledBy, options, value, default: fallback, onChange, onPin }: Props) {
  // A provider that reports no prices (comfy) gets no price columns and no cost sort.
  const priced = options.some((o) => o.image_per_m != null || o.per_image != null)
  const [sort, setSort] = useState<Sort>('newest')
  const [filter, setFilter] = useState('')
  const chosen = value || fallback
  const needle = filter.trim().toLowerCase()
  const matching = options.filter((o) => !needle || `${o.id} ${o.label}`.toLowerCase().includes(needle))
  const ordered = priced && sort === 'cheapest' ? [...matching].sort((a, b) => cost(a) - cost(b)) : matching
  const sections = [
    { title: 'Pinned', rows: ordered.filter((o) => o.pinned) },
    { title: priced && sort === 'cheapest' ? 'Cheapest' : 'Newest', rows: ordered.filter((o) => !o.pinned) },
  ].filter((s) => s.rows.length > 0)
  const listed = options.some((o) => o.id === value)

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
        {priced && (
          <div className="model-list-sort" role="group" aria-label="Sort models">
            {(['newest', 'cheapest'] as const).map((s) => (
              <button key={s} type="button" aria-pressed={sort === s} onClick={() => setSort(s)}>
                {s === 'newest' ? 'Newest' : 'Cheapest'}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className={`model-list-rows${priced ? '' : ' is-unpriced'}`} role="radiogroup" aria-labelledby={labelledBy}>
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
                  {priced && (
                    <>
                      <span className={`model-list-cost${o.per_image != null ? ' is-measured' : ''}`}>{price.perPicture}</span>
                      <span className="model-list-price">{price.list}</span>
                    </>
                  )}
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
          value={listed ? '' : value}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    </div>
  )
}
