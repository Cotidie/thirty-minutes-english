import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
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
    render(<ExpressionsTab items={items} />)
    const note = screen.getByRole('button', { name: /Neutral to workplace register/ })
    expect(note).toHaveClass('is-clamped')
    await userEvent.click(note)
    expect(note).not.toHaveClass('is-clamped')
  })
})
