import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TopicPicker } from './TopicPicker'
import type { Topic } from '../types'

const suggestions: Topic[] = [
  { text: 'Who pays when the grid runs short', category: 'news' },
  { text: 'Digital twins in manufacturing', category: 'tech' },
  { text: 'The Cold War space race', category: 'history' },
]

describe('TopicPicker', () => {
  it('tags each chip with its category so the colour can follow', () => {
    render(<TopicPicker suggestions={suggestions} busy={false} onGenerate={vi.fn()} />)
    for (const s of suggestions) {
      expect(screen.getByRole('button', { name: s.text })).toHaveAttribute('data-category', s.category)
    }
  })

  it('keys only the categories the day actually offers', () => {
    render(<TopicPicker suggestions={suggestions} busy={false} onGenerate={vi.fn()} />)
    const key = screen.getByRole('list', { name: 'Topic categories' })
    expect(key).toHaveTextContent('In the news')
    expect(key).toHaveTextContent('Technology')
    expect(key).toHaveTextContent('History')
    expect(key).not.toHaveTextContent('Literature')
  })

  it('fills the input from a chip and generates that topic', async () => {
    const onGenerate = vi.fn()
    render(<TopicPicker suggestions={suggestions} busy={false} onGenerate={onGenerate} />)

    await userEvent.click(screen.getByRole('button', { name: 'The Cold War space race' }))
    expect(screen.getByLabelText("Today's topic")).toHaveValue('The Cold War space race')

    await userEvent.click(screen.getByRole('button', { name: 'Generate session' }))
    expect(onGenerate).toHaveBeenCalledWith('The Cold War space race')
  })
})
