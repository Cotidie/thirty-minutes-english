import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ExpressionsTab } from './ExpressionsTab'

const items = [
  {
    phrase: 'a moving target',
    meaning: 'something that keeps changing',
    usage_note: 'Neutral to workplace register. ' + 'Extra detail. '.repeat(30),
    examples: ['The spec is a moving target.', 'Deadlines here are a moving target.'],
  },
]

describe('ExpressionsTab', () => {
  it('clamps the usage note until it is clicked', async () => {
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} />)
    const note = screen.getByRole('button', { name: /Neutral to workplace register/ })
    expect(note).toHaveClass('is-clamped')
    await userEvent.click(note)
    expect(note).not.toHaveClass('is-clamped')
  })

  it('stars an expression by its phrase and shows it as pressed', async () => {
    const onToggleStar = vi.fn()
    const { rerender } = render(<ExpressionsTab items={items} starred={[]} onToggleStar={onToggleStar} />)
    const star = screen.getByRole('button', { name: 'Star a moving target' })
    expect(star).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(star)
    expect(onToggleStar).toHaveBeenCalledWith('a moving target')

    rerender(<ExpressionsTab items={items} starred={['a moving target']} onToggleStar={onToggleStar} />)
    expect(screen.getByRole('button', { name: 'Star a moving target' })).toHaveAttribute('aria-pressed', 'true')
  })
})
