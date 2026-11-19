import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderInRoom, someoneSets, viewsSent } from '../test/presenceRoom'
import type { Expression } from '../types'
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

  const sentence = { korean: '마감이 계속 바뀌어.', english: 'The deadline is a moving target.' }
  const dialogue = [
    { korean: '요즘 일정 어때?', english: 'How is the schedule these days?' },
    { korean: '마감이 자꾸 바뀌어서 정신없어.', english: "The deadline is a moving target, so it's chaos." },
  ]
  const both = [{ ...items[0], korean_example: sentence, korean_dialogue: dialogue }]
  const practice = () => screen.getByRole('group', { name: '연습 방식' })

  it('shows the dialogue first, with a toggle to the one sentence, when the expression has both', () => {
    render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(within(practice()).getByRole('button', { name: '대화' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(practice()).getByRole('button', { name: '한 문장' })).toHaveAttribute('aria-pressed', 'false')
    const card = screen.getByRole('button', { name: /요즘 일정 어때\?/ })
    expect(card).toHaveAttribute('aria-pressed', 'false')
    for (const text of ['A', 'B', '요즘 일정 어때?', '마감이 자꾸 바뀌어서 정신없어.', '영어로 어떻게 말할까요?']) {
      expect(within(card).getByText(text)).toBeInTheDocument()
    }
    expect(screen.queryByText('마감이 계속 바뀌어.')).toBeNull()
  })

  it('flips both lines of the dialogue to English at once and back', async () => {
    render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    const card = screen.getByRole('button', { name: /요즘 일정 어때\?/ })
    await userEvent.click(card)
    expect(card).toHaveAttribute('aria-pressed', 'true')
    expect(within(card).getByText('How is the schedule these days?')).toBeInTheDocument()
    expect(within(card).getAllByText('a moving target', { selector: 'mark' })).toHaveLength(1)
    expect(within(card).queryByText('요즘 일정 어때?')).toBeNull()
    expect(within(card).getByText('모범 답안 · 다르게 말해도 표현을 넣었으면 충분해요')).toBeInTheDocument()
    await userEvent.click(card)
    expect(within(card).getByText('요즘 일정 어때?')).toBeInTheDocument()
  })

  it('marks only the line that uses the expression, not one that shares two of its words', async () => {
    const tellMe = [
      {
        ...items[0],
        phrase: 'Tell me about it',
        korean_dialogue: [
          { korean: '오늘 밤에 생각해 볼게.', english: "I'll think about it tonight." },
          { korean: '내 말이, 우리 상사도 그래.', english: 'Tell me about it, my boss does the same.' },
        ],
      },
    ]
    render(<ExpressionsTab items={tellMe} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    const card = screen.getByRole('button', { name: /오늘 밤에 생각해 볼게\./ })
    await userEvent.click(card)
    expect(within(card).getAllByText(/about it/, { selector: 'mark' }).map((mark) => mark.textContent)).toEqual(['Tell me about it'])
    expect(within(card).getByText("I'll think about it tonight.")).toBeInTheDocument()
  })

  it('switches to the one sentence and back with the toggle', async () => {
    render(<ExpressionsTab items={both} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    await userEvent.click(within(practice()).getByRole('button', { name: '한 문장' }))
    expect(within(practice()).getByRole('button', { name: '한 문장' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /마감이 계속 바뀌어\./ })).toBeInTheDocument()
    expect(screen.queryByText('요즘 일정 어때?')).toBeNull()
    await userEvent.click(within(practice()).getByRole('button', { name: '대화' }))
    expect(screen.getByText('요즘 일정 어때?')).toBeInTheDocument()
  })

  it('shows only the dialogue, with no toggle, when the expression has no one sentence', () => {
    render(<ExpressionsTab items={[{ ...items[0], korean_dialogue: dialogue }]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.queryByRole('group', { name: '연습 방식' })).toBeNull()
    expect(screen.getByText('한국어로 해 보기')).toBeInTheDocument()
    expect(screen.getByText('요즘 일정 어때?')).toBeInTheDocument()
  })

  it('shows only the one sentence, with no toggle, when the expression has no dialogue', () => {
    render(<ExpressionsTab items={[{ ...items[0], korean_example: sentence }]} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />)
    expect(screen.queryByRole('group', { name: '연습 방식' })).toBeNull()
    expect(screen.getByText('마감이 계속 바뀌어.')).toBeInTheDocument()
  })
})

describe('ExpressionsTab with someone else in the session', () => {
  const tab = (list: Expression[]) => <ExpressionsTab items={list} starred={[]} onToggleStar={vi.fn()} onSwap={vi.fn()} onAdd={vi.fn()} />

  it('turns over the chip someone else turned over, and tells them when I do', async () => {
    const { socket } = renderInRoom(tab([{ ...items[0], korean: '움직이는 과녁' }]))
    someoneSets(socket, 'chip:expression:21', true)
    const chip = screen.getByRole('button', { name: 'Hide the Korean for a moving target' })
    expect(chip).toHaveTextContent('움직이는 과녁')
    await userEvent.click(chip)
    expect(viewsSent(socket)).toEqual([{ key: 'chip:expression:21', value: false }])
  })

  it('flips the Korean card with them', async () => {
    const { socket } = renderInRoom(tab([{ ...items[0], korean_example: { korean: '목표가 자꾸 바뀌어.', english: 'It is a moving target.' } }]))
    expect(screen.getByText('목표가 자꾸 바뀌어.')).toBeInTheDocument()
    someoneSets(socket, 'example:21', true)
    expect(screen.queryByText('목표가 자꾸 바뀌어.')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { pressed: true }))
    expect(viewsSent(socket)).toEqual([{ key: 'example:21', value: false }])
  })

  it('switches the mode and flips the dialogue with them', async () => {
    const both = [
      {
        ...items[0],
        korean_example: { korean: '목표가 자꾸 바뀌어.', english: 'It is a moving target.' },
        korean_dialogue: [
          { korean: '요즘 일정 어때?', english: 'How is the schedule?' },
          { korean: '목표가 자꾸 바뀌어.', english: 'It is a moving target.' },
        ],
      },
    ]
    const { socket } = renderInRoom(tab(both))
    someoneSets(socket, 'mode:21', 'solo')
    expect(screen.queryByText('요즘 일정 어때?')).toBeNull()
    someoneSets(socket, 'mode:21', 'dialogue')
    someoneSets(socket, 'dialogue:21', true)
    expect(screen.getByText('How is the schedule?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '한 문장' }))
    expect(viewsSent(socket)).toEqual([{ key: 'mode:21', value: 'solo' }])
  })
})
