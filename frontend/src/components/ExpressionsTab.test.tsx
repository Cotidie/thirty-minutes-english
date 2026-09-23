import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Example } from '../types'
import { ExpressionsTab } from './ExpressionsTab'

vi.mock('../api', () => ({ api: { addExample: vi.fn() } }))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn() }))

const none: Example[] = []

const items = [
  {
    phrase: 'a moving target',
    meaning: 'something that keeps changing',
    usage_note: 'Neutral to workplace register. ' + 'Extra detail. '.repeat(30),
    examples: ['The spec is a moving target.', 'Deadlines here are a moving target.'],
  },
]

describe('ExpressionsTab', () => {
  it('keeps the Korean behind a chip beside the phrase until tapped', async () => {
    const withKorean = [{ ...items[0], korean: '일부러 반대 입장을 취하다' }, ...items.slice(1)]
    render(<ExpressionsTab items={withKorean} sessionId={1} starred={[]} onToggleStar={vi.fn()} examples={[]} onExample={vi.fn()} />)
    expect(screen.queryByText('일부러 반대 입장을 취하다')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: `Korean for ${items[0].phrase}` }))
    expect(screen.getByRole('button', { name: `Hide the Korean for ${items[0].phrase}` })).toHaveTextContent('일부러 반대 입장을 취하다')
  })

  it('shows the synonyms under the meaning', () => {
    render(<ExpressionsTab items={[{ ...items[0], synonyms: ['a shifting goal'] }]} sessionId={1} starred={[]} onToggleStar={vi.fn()} examples={[]} onExample={vi.fn()} />)
    expect(screen.getByText('something that keeps changing')).toHaveTextContent('something that keeps changing≈ a shifting goal')
  })

  it('marks the expression where each example uses it', () => {
    render(<ExpressionsTab items={items} sessionId={1} starred={[]} onToggleStar={vi.fn()} examples={[]} onExample={vi.fn()} />)
    expect(screen.getAllByText('a moving target', { selector: 'mark' })).toHaveLength(2)
  })

  it('clamps the usage note until it is clicked', async () => {
    render(<ExpressionsTab items={items} sessionId={3} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const note = screen.getByRole('button', { name: /Neutral to workplace register/ })
    expect(note).toHaveClass('is-clamped')
    await userEvent.click(note)
    expect(note).not.toHaveClass('is-clamped')
  })

  it('stars an expression by its phrase and shows it as pressed', async () => {
    const onToggleStar = vi.fn()
    const { rerender } = render(
      <ExpressionsTab items={items} sessionId={3} starred={[]} onToggleStar={onToggleStar} examples={none} onExample={vi.fn()} />,
    )
    const star = screen.getByRole('button', { name: 'Star a moving target' })
    expect(star).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(star)
    expect(onToggleStar).toHaveBeenCalledWith('a moving target')

    rerender(
      <ExpressionsTab items={items} sessionId={3} starred={['a moving target']} onToggleStar={onToggleStar} examples={none} onExample={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Star a moving target' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows each sentence under its own expression, behind the Your turn label', () => {
    const examples: Example[] = [
      { id: 1, created_at: '', session_id: 3, expression: 'a moving target', user_text: 'The spec moved.', coach_text: 'The spec is a moving target. Natural.', seconds: 9 },
      { id: 2, created_at: '', session_id: 3, expression: 'some other phrase', user_text: 'Elsewhere.', coach_text: 'Elsewhere.', seconds: 9 },
    ]
    render(<ExpressionsTab items={items} sessionId={3} starred={[]} onToggleStar={vi.fn()} examples={examples} onExample={vi.fn()} />)
    expect(screen.getByText('The spec moved.')).toBeInTheDocument()
    expect(screen.queryByText('Elsewhere.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Your turn: one sentence each.' })).toBeInTheDocument()
  })
})
