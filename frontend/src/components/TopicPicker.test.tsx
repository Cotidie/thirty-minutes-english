import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TopicPicker } from './TopicPicker'
import type { Topic } from '../types'

const suggestions: Topic[] = [
  { text: 'Who pays when the grid runs short', category: 'news' },
  { text: 'Digital twins in manufacturing', category: 'ie' },
  { text: "Korea's birth rate and what could reverse it", category: 'korea' },
  { text: 'How to read a paper in an hour', category: 'research' },
  { text: 'The Cold War space race', category: 'history' },
]

const labels = {
  news: 'In the news',
  korea: 'Korea',
  research: 'Research',
  cs: 'Computer science',
  ie: 'Industrial engineering',
  history: 'History',
}

describe('TopicPicker', () => {
  it('tags each chip with its category so the colour can follow', () => {
    render(<TopicPicker suggestions={suggestions} labels={labels} pending={false} busy={false} onGenerate={vi.fn()} onRefresh={vi.fn()} />)
    for (const s of suggestions) {
      expect(screen.getByRole('button', { name: s.text })).toHaveAttribute('data-category', s.category)
    }
  })

  it('keys only the categories the day actually offers', () => {
    render(<TopicPicker suggestions={suggestions} labels={labels} pending={false} busy={false} onGenerate={vi.fn()} onRefresh={vi.fn()} />)
    const key = screen.getByRole('list', { name: 'Topic categories' })
    expect(key).toHaveTextContent('In the news')
    expect(key).toHaveTextContent('Korea')
    expect(key).toHaveTextContent('Research')
    expect(key).toHaveTextContent('Industrial engineering')
    expect(key).toHaveTextContent('History')
    expect(key).not.toHaveTextContent('Literature')
  })

  it('fills the input from a chip and generates that topic', async () => {
    const onGenerate = vi.fn()
    render(<TopicPicker suggestions={suggestions} labels={labels} pending={false} busy={false} onGenerate={onGenerate} onRefresh={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: 'The Cold War space race' }))
    expect(screen.getByLabelText("Today's topic")).toHaveValue('The Cold War space race')

    await userEvent.click(screen.getByRole('button', { name: 'Generate session' }))
    expect(onGenerate).toHaveBeenCalledWith('The Cold War space race')
  })

  it('has a refresh button that waits while the news half is pending', async () => {
    const onRefresh = vi.fn()
    const { rerender } = render(
      <TopicPicker suggestions={suggestions} labels={labels} pending={false} busy={false} onGenerate={vi.fn()} onRefresh={onRefresh} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }))
    expect(onRefresh).toHaveBeenCalledTimes(1)

    rerender(<TopicPicker suggestions={suggestions} labels={labels} pending={true} busy={false} onGenerate={vi.fn()} onRefresh={onRefresh} />)
    expect(screen.getByRole('button', { name: 'Refresh suggestions' })).toBeDisabled()
  })

  it('says why the news half is missing once the fetch has given up', () => {
    render(
      <TopicPicker suggestions={suggestions} labels={labels} pending={false} error="claude exited 1" busy={false} onGenerate={vi.fn()} onRefresh={vi.fn()} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent("Today's news could not be fetched: claude exited 1")
  })

  it('keeps the old failure quiet while a new fetch is running', () => {
    render(
      <TopicPicker suggestions={suggestions} labels={labels} pending={true} error="claude exited 1" busy={false} onGenerate={vi.fn()} onRefresh={vi.fn()} />,
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
