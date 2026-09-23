import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SettingOption } from '../types'
import { ModelList, priceOf } from './ModelList'

const model = (id: string, extra: Partial<SettingOption> = {}): SettingOption => ({
  id,
  label: '',
  description: '',
  efforts: null,
  ...extra,
})

const OPTIONS = [
  model('google/gemini-3-pro-image', { label: 'Nano Banana Pro', image_per_m: 120, per_image: 0.134, per_image_count: 12, pinned: true }),
  model('recraft/v4-flash', { label: 'Recraft V4.1 Flash', image_per_m: 1.68 }),
  model('openai/gpt-image-2.5', { label: 'GPT Image 2.5', image_per_m: 30 }),
]

function renderList(value = '', onChange = vi.fn(), onPin = vi.fn()) {
  render(
    <>
      <span id="l">IMAGE_MODEL</span>
      <ModelList
        name="image"
        labelledBy="l"
        options={OPTIONS}
        value={value}
        default="google/gemini-3-pro-image"
        onChange={onChange}
        onPin={onPin}
      />
    </>,
  )
  return { onChange, onPin }
}

describe('priceOf', () => {
  it('leads with what a picture cost here, then the list price', () => {
    expect(priceOf(OPTIONS[0])).toEqual({ perPicture: '≈ $0.13 / picture · 12 drawn', list: '$120 / 1M tok' })
    expect(priceOf(OPTIONS[1])).toEqual({ perPicture: 'no picture yet', list: '$1.68 / 1M tok' })
  })
})

describe('ModelList', () => {
  it('shows pinned models first, the default checked when nothing is saved', () => {
    renderList()
    const radios = screen.getAllByRole('radio')
    expect(radios.map((r) => r.closest('label')?.textContent)).toEqual(['Nano Banana Pro', 'Recraft V4.1 Flash', 'GPT Image 2.5'])
    expect(radios[0]).toBeChecked()
    expect(screen.getByText('Pinned')).toBeInTheDocument()
  })

  it('picks a model by its row and pins from the row', async () => {
    const { onChange, onPin } = renderList()
    await userEvent.click(screen.getByLabelText('GPT Image 2.5'))
    expect(onChange).toHaveBeenCalledWith('openai/gpt-image-2.5')
    await userEvent.click(screen.getByRole('button', { name: 'Pin Recraft V4.1 Flash' }))
    expect(onPin).toHaveBeenCalledWith('recraft/v4-flash', true)
    await userEvent.click(screen.getByRole('button', { name: 'Unpin Nano Banana Pro' }))
    expect(onPin).toHaveBeenCalledWith('google/gemini-3-pro-image', false)
  })

  it('sorts the unpinned models by cost and filters by name', async () => {
    renderList()
    await userEvent.click(screen.getByRole('button', { name: 'Cheapest' }))
    const cheapest = screen.getByText('Cheapest', { selector: 'p' }).closest('div')!
    expect(within(cheapest).getAllByRole('radio').map((r) => r.closest('label')?.textContent)).toEqual([
      'Recraft V4.1 Flash',
      'GPT Image 2.5',
    ])
    await userEvent.type(screen.getByLabelText('Filter models'), 'gpt')
    expect(screen.getAllByRole('radio')).toHaveLength(1)
  })

  it('takes a model id the provider does not list', async () => {
    const onChange = vi.fn()
    renderList('some/new-model', onChange)
    expect(screen.getAllByRole('radio').every((r) => !(r as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByLabelText('Other model id')).toHaveValue('some/new-model')
  })
})

describe('ModelList without prices', () => {
  it('drops the price columns and the cost sort', () => {
    render(
      <ModelList
        name="image"
        labelledBy="l"
        options={[model('vertexai/nano-banana-pro'), model('xai/grok-image-generate')]}
        value=""
        default="vertexai/nano-banana-pro"
        onChange={vi.fn()}
        onPin={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Cheapest' })).not.toBeInTheDocument()
    expect(screen.queryByText('no picture yet')).not.toBeInTheDocument()
  })
})
