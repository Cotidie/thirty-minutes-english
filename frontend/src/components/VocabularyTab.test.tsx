import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Example } from '../types'
import { VocabularyTab } from './VocabularyTab'

vi.mock('../api', () => ({ api: { addExample: vi.fn() } }))
vi.mock('../lib/liveClient', () => ({ connectExample: vi.fn() }))

const none: Example[] = []

const items = [
  { word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are ubiquitous.' },
  { word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated the risk.' },
]

describe('VocabularyTab', () => {
  it('shows the word and example but hides the definition until clicked', async () => {
    render(<VocabularyTab items={items} sessionId={3} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    expect(screen.getByText('ubiquitous')).toBeInTheDocument()
    expect(screen.getByText('Phones are ubiquitous.')).toBeInTheDocument()
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^ubiquitous/ }))
    expect(screen.getByText('present everywhere')).toBeInTheDocument()
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })

  it('hides the definition again on a second click', async () => {
    render(<VocabularyTab items={items} sessionId={3} starred={[]} onToggleStar={vi.fn()} examples={none} onExample={vi.fn()} />)
    const card = screen.getByRole('button', { name: /^mitigate/ })
    await userEvent.click(card)
    expect(screen.getByText('make less severe')).toBeInTheDocument()
    await userEvent.click(card)
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })

  it('stars a word without flipping its card', async () => {
    const onToggleStar = vi.fn()
    render(<VocabularyTab items={items} sessionId={3} starred={['mitigate']} onToggleStar={onToggleStar} examples={none} onExample={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Star mitigate' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: 'Star ubiquitous' }))
    expect(onToggleStar).toHaveBeenCalledWith('ubiquitous')
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()
  })

  it('gives each word a Practice button with its own sentences under it', () => {
    const examples: Example[] = [
      { id: 1, created_at: '', session_id: 3, expression: 'mitigate', user_text: 'We mitigated the delay.', coach_text: 'We mitigated the delay. Natural.', seconds: 9 },
    ]
    render(<VocabularyTab items={items} sessionId={3} starred={[]} onToggleStar={vi.fn()} examples={examples} onExample={vi.fn()} />)
    expect(screen.getAllByRole('button', { name: 'Practice' })).toHaveLength(2)
    expect(screen.getByText('We mitigated the delay.')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sentences with mitigate' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Sentences with ubiquitous' })).not.toBeInTheDocument()
  })
})
