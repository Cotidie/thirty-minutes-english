import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ArticleTab } from './ArticleTab'

vi.mock('../lib/liveClient', () => ({
  connectReadAloud: vi.fn(async () => ({ microphone: {}, finish: vi.fn(), close: vi.fn(), dispose: vi.fn() })),
}))

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
    render(<ArticleTab article={article} sessionId={3} />)
    expect(document.querySelector('mark')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(document.querySelector('mark')).toHaveTextContent('Upkeep is what actually pays.')

    await userEvent.click(screen.getByRole('button', { name: 'What pays?' }))
    expect(document.querySelector('mark')).toBeNull()
  })

  it('lists sources as links when present and hides the block when absent', () => {
    const { unmount } = render(
      <ArticleTab
        article={{ ...article, sources: [{ title: 'Kafka - Britannica', url: 'https://www.britannica.com/kafka' }] }}
        sessionId={3}
      />,
    )
    const link = screen.getByRole('link', { name: 'Kafka - Britannica' })
    expect(link).toHaveAttribute('href', 'https://www.britannica.com/kafka')
    expect(screen.getByText('britannica.com')).toBeInTheDocument()
    unmount()

    render(<ArticleTab article={article} sessionId={3} />)
    expect(screen.queryByText('Sources')).toBeNull()
  })

  it('renders a question without evidence as plain text', () => {
    render(<ArticleTab article={article} sessionId={3} />)
    expect(screen.queryByRole('button', { name: 'Legacy question' })).toBeNull()
    expect(screen.getByText('Legacy question')).toBeInTheDocument()
  })

  it('offers Read aloud under each paragraph and lets only one paragraph hold the microphone', async () => {
    render(<ArticleTab article={article} sessionId={3} />)
    const buttons = screen.getAllByRole('button', { name: 'Read aloud' })
    expect(buttons).toHaveLength(2)

    await userEvent.click(buttons[0])
    expect(screen.getByRole('status')).toHaveTextContent('Connecting')
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeDisabled()
  })
})

describe('ArticleTab open question', () => {
  it('marks the question the article does not answer and leaves it unclickable', async () => {
    render(
      <ArticleTab
        article={{
          ...article,
          questions: [
            { text: 'What pays?', evidence: ['Upkeep is what actually pays.'] },
            { text: 'Would you fund a twin you could not maintain?', evidence: [] },
          ],
        }}
        sessionId={3}
      />,
    )
    expect(screen.getByRole('button', { name: 'What pays?' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Would you fund/ })).not.toBeInTheDocument()
    expect(screen.getByText('your take')).toBeInTheDocument()
  })

  it('flips a sentence to its Korean once the English has sunk, and back on the next click', async () => {
    const translated = {
      ...article,
      translation: [
        { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
        { en: 'Upkeep is what actually pays.', ko: '유지가 진짜 돈이 든다.' },
      ],
    }
    render(<ArticleTab article={translated} sessionId={3} />)
    const sentence = screen.getByRole('button', { name: 'Upkeep is what actually pays.' })
    expect(screen.queryByText('유지가 진짜 돈이 든다.')).not.toBeInTheDocument()

    await userEvent.click(sentence)
    expect(sentence).toHaveClass('is-sinking')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('유지가 진짜 돈이 든다.')
    expect(sentence).toHaveClass('is-ko', 'is-rising')
    expect(sentence).toHaveAttribute('lang', 'ko')
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveClass('is-still')

    await userEvent.click(sentence)
    fireEvent.animationEnd(sentence)
    expect(sentence).toHaveTextContent('Upkeep is what actually pays.')
    expect(sentence).not.toHaveAttribute('lang')
    // The untranslated paragraph stays plain text, not a button.
    expect(screen.queryByRole('button', { name: 'A modest twin delivers more value.' })).not.toBeInTheDocument()
  })

  it('still marks evidence inside a translated sentence, and across two of them', async () => {
    const translated = {
      ...article,
      questions: [{ text: 'Both?', evidence: ['cheap. Upkeep is what'] }],
      translation: [
        { en: 'Ambition is cheap.', ko: '야심은 싸다.' },
        { en: 'Upkeep is what actually pays.', ko: '유지가 진짜 돈이 든다.' },
      ],
    }
    render(<ArticleTab article={translated} sessionId={3} />)
    await userEvent.click(screen.getByRole('button', { name: 'Both?' }))
    const marks = [...document.querySelectorAll('mark')].map((m) => m.textContent)
    expect(marks).toEqual(['cheap.', ' ', 'Upkeep is what'])
  })
})
