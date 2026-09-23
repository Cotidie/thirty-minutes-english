import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ModelCombo, priceOf } from './Choice'

const gemini = {
  id: 'google/gemini-3-pro-image',
  label: 'Gemini 3 Pro Image',
  description: '',
  efforts: null,
  image_per_m: 120,
  text_per_m: 2,
  per_image: 0.134,
  per_image_count: 12,
}
const recraft = { id: 'recraft/v4', label: '', description: '', efforts: null, image_per_m: 1.68, text_per_m: 0 }

describe('priceOf', () => {
  it('leads with what a picture cost here, then the list price', () => {
    expect(priceOf(gemini)).toEqual({
      perPicture: '≈ $0.13 / picture · 12 drawn',
      list: ['$120 / 1M image tok', '$2.00 / 1M text tok'],
    })
    expect(priceOf(recraft)).toEqual({ perPicture: 'No picture drawn yet', list: ['$1.68 / 1M image tok'] })
    expect(priceOf({ id: 'opus', label: '', description: '', efforts: [] })).toBeNull()
  })
})

describe('ModelCombo', () => {
  it('prices each image model in the menu and the chosen one under the field', async () => {
    render(
      <>
        <span id="l">IMAGE_MODEL</span>
        <ModelCombo labelledBy="l" options={[gemini, recraft]} value="" placeholder="google/gemini-3-pro-image" onChange={() => undefined} />
      </>,
    )
    expect(screen.getByText('≈ $0.13 / picture · 12 drawn · $120 / 1M image tok · $2.00 / 1M text tok')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('combobox'))
    const options = await screen.findAllByRole('option')
    expect(options[1]).toHaveTextContent('No picture drawn yet')
    expect(options[1]).toHaveTextContent('$1.68 / 1M image tok')
  })
})
