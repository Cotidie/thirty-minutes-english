import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ArticleTab } from './ArticleTab'

const article = {
  title: 'Twins',
  body: 'Ambition is cheap. Upkeep is what actually pays.\n\nA modest twin delivers more value.',
  questions: [
    { text: 'What pays?', evidence: ['Upkeep is what actually pays.'] },
    { text: 'Legacy question', evidence: [] },
  ],
}

describe('ArticleTab', () => {
  it('marks the evidence in the body when a question is clicked, and clears it on a second click', async () => {
    render(<ArticleTab article={article} />)
    expect(document.querySelector('mark')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(document.querySelector('mark')).toHaveTextContent('Upkeep is what actually pays.')

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(document.querySelector('mark')).toBeNull()
  })

  it('renders a question without evidence as plain text', () => {
    render(<ArticleTab article={article} />)
    expect(screen.queryByRole('button', { name: 'Legacy question' })).toBeNull()
    expect(screen.getByText('Legacy question')).toBeInTheDocument()
  })
})
