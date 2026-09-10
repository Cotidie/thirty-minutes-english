import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { VocabularyTab } from './VocabularyTab'

const items = [
  { word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are ubiquitous.' },
  { word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated the risk.' },
]

describe('VocabularyTab', () => {
  it('shows the word and example but hides the definition until clicked', async () => {
    render(<VocabularyTab items={items} />)
    expect(screen.getByText('ubiquitous')).toBeInTheDocument()
    expect(screen.getByText('Phones are ubiquitous.')).toBeInTheDocument()
    expect(screen.queryByText('present everywhere')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /ubiquitous/ }))
    expect(screen.getByText('present everywhere')).toBeInTheDocument()
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })

  it('hides the definition again on a second click', async () => {
    render(<VocabularyTab items={items} />)
    const card = screen.getByRole('button', { name: /mitigate/ })
    await userEvent.click(card)
    expect(screen.getByText('make less severe')).toBeInTheDocument()
    await userEvent.click(card)
    expect(screen.queryByText('make less severe')).not.toBeInTheDocument()
  })
})
