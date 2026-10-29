import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ExpressionsTab } from './ExpressionsTab'

const items = [
  {
    id: 21,
    phrase: 'a moving target',
    meaning: 'something that keeps changing',
    usage_note: 'Neutral to workplace register. ' + 'Extra detail. '.repeat(30),
    examples: ['The spec is a moving target.', 'Deadlines here are a moving target.'],
  },
]

describe('ExpressionsTab', () => {
  it('keeps the Korean behind a chip beside the phrase until tapped', async () => {
    const withKorean = [{ ...items[0], korean: '일부러 반대 입장을 취하다' }, ...items.slice(1)]
    render(<ExpressionsTab items={withKorean} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.queryByText('일부러 반대 입장을 취하다')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: `Korean for ${items[0].phrase}` }))
    expect(screen.getByRole('button', { name: `Hide the Korean for ${items[0].phrase}` })).toHaveTextContent('일부러 반대 입장을 취하다')
  })

  it('shows the synonyms under the meaning', () => {
    render(<ExpressionsTab items={[{ ...items[0], synonyms: ['a shifting goal'] }]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getByText('something that keeps changing')).toHaveTextContent('something that keeps changing≈ a shifting goal')
  })

  it('marks the expression where each example uses it', () => {
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getAllByText('a moving target', { selector: 'mark' })).toHaveLength(2)
  })

  it('shows the usage note whole, as plain text', () => {
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getByText(/Neutral to workplace register/)).toHaveClass('expression-note')
    expect(screen.queryByRole('button', { name: /Neutral to workplace register/ })).not.toBeInTheDocument()
  })

  it('stars an expression by its id and shows it as pressed', async () => {
    const onToggleStar = vi.fn()
    const { rerender } = render(
      <ExpressionsTab items={items} starred={[]} onToggleStar={onToggleStar} onSwap={vi.fn()} onAdd={vi.fn()} />,
    )
    const star = screen.getByRole('button', { name: 'Star a moving target' })
    expect(star).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(star)
    expect(onToggleStar).toHaveBeenCalledWith(21)

    rerender(
      <ExpressionsTab items={items} starred={[21]} onToggleStar={onToggleStar} onSwap={vi.fn()} onAdd={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Star a moving target' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('says so when a session has no expressions', () => {
    render(<ExpressionsTab items={[]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getByText('This session has no expressions.')).toBeInTheDocument()
    expect(document.querySelector('.expression-list')).toBeNull()
  })

  it('swaps an expression for another, one press at a time', async () => {
    let done = () => {}
    const onSwap = vi.fn(() => new Promise<void>((resolve) => (done = resolve)))
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={onSwap} onAdd={vi.fn()} />)
    const swap = screen.getByRole('button', { name: 'Swap a moving target for another expression' })
    await userEvent.click(swap)
    expect(onSwap).toHaveBeenCalledWith(21)
    expect(swap).toBeDisabled()
    done()
    await waitFor(() => expect(swap).toBeEnabled())
  })

  it('says so when a swap fails', async () => {
    const onSwap = vi.fn(async () => {
      throw new Error('nothing is left to swap in')
    })
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={onSwap} onAdd={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Swap a moving target for another expression' }))
    expect(await screen.findByText('Could not swap it: nothing is left to swap in')).toBeInTheDocument()
  })

  it('adds another expression from the wide button below the list, one change at a time', async () => {
    let done = () => {}
    const onAdd = vi.fn(() => new Promise<void>((resolve) => (done = resolve)))
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={onAdd} />)
    const add = screen.getByRole('button', { name: 'Add another expression' })
    expect(add.compareDocumentPosition(document.querySelector('.expression-list')!)).toBe(Node.DOCUMENT_POSITION_PRECEDING)
    await userEvent.click(add)
    expect(onAdd).toHaveBeenCalledOnce()
    expect(add).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Swap a moving target for another expression' })).toBeDisabled()
    done()
    await waitFor(() => expect(add).toBeEnabled())
  })

  it('offers to add one when the session has none', () => {
    render(<ExpressionsTab items={[]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Add another expression' })).toBeInTheDocument()
  })

  it('says so when adding fails', async () => {
    const onAdd = vi.fn(async () => {
      throw new Error('nothing is left to add')
    })
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={onAdd} />)
    await userEvent.click(screen.getByRole('button', { name: 'Add another expression' }))
    expect(await screen.findByText('Could not add one: nothing is left to add')).toBeInTheDocument()
  })

  it('flips the Korean example under the examples to its English model answer and back', async () => {
    const withExample = [{ ...items[0], korean_example: { korean: '마감이 계속 바뀌어.', english: 'The deadline is a moving target.' } }]
    render(<ExpressionsTab items={withExample} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    const example = screen.getByRole('button', { name: /마감이 계속 바뀌어\./ })
    expect(document.querySelector('.expression-examples')!.compareDocumentPosition(example)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
    expect(within(example).getByText('영어로 어떻게 말할까요?')).toBeInTheDocument()
    expect(example).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText(/The deadline is/)).toBeNull()

    await userEvent.click(example)
    expect(example).toHaveAttribute('aria-pressed', 'true')
    expect(within(example).getByText('a moving target', { selector: 'mark' })).toBeInTheDocument()
    expect(screen.queryByText('마감이 계속 바뀌어.')).toBeNull()
    expect(within(example).queryByText('영어로 어떻게 말할까요?')).toBeNull()

    await userEvent.click(example)
    expect(within(example).getByText('마감이 계속 바뀌어.')).toBeInTheDocument()
  })

  it('leaves the Korean example out when the expression has none', () => {
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(document.querySelector('.korean-example')).toBeNull()
  })

  it('gives an expression no Your turn', () => {
    render(<ExpressionsTab items={items} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Your turn/ })).toBeNull()
  })
})
