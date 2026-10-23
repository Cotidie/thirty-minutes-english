import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Example, SessionContent, Stars } from '../types'
import { SummaryTab } from './SummaryTab'

vi.mock('../api', () => ({ api: { listExamples: vi.fn(), listReadings: vi.fn(), listSummaries: vi.fn() } }))

const content: SessionContent = {
  topic: 'Twins',
  expressions: [
    { phrase: 'a moving target', meaning: 'something that keeps changing', usage_note: '', examples: [] },
    { phrase: 'on the fence', meaning: 'undecided', usage_note: '', examples: [] },
  ],
  article: { title: 'Twins', body: '', questions: [] },
  vocabulary: [
    { word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated it.' },
    { word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are.' },
  ],
}

const none: Stars = { expressions: [], words: [] }

const example: Example = {
  id: 9,
  created_at: '',
  session_id: 3,
  expression: 'on the fence',
  user_text: "I'm on the fence about the offer.",
  coach_text: "I'm on the fence about the offer. That's how a native speaker would say it.",
  seconds: 11,
}

beforeEach(() => {
  vi.mocked(api.listExamples).mockResolvedValue([example])
  vi.mocked(api.listSummaries).mockResolvedValue([])
})

describe('SummaryTab', () => {
  it('shows the sentences made, for this session only', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)

    expect(await screen.findByText("I'm on the fence about the offer.")).toBeInTheDocument()
    expect(screen.getByText(/That's how a native speaker would say it/)).toBeInTheDocument()
    expect(vi.mocked(api.listExamples)).toHaveBeenCalledWith(3)
  })

  it('leaves the note to its button and the read-aloud marks to the article', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText("I'm on the fence about the offer.")
    const titles = [...document.querySelectorAll('.summary-title')].map((t) => t.firstChild?.textContent)
    expect(titles).toEqual(['Starred', 'Sentences you made', 'Paragraphs you summed up'])
    expect(vi.mocked(api.listReadings)).not.toHaveBeenCalled()
  })

  it('counts each section', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText("I'm on the fence about the offer.")
    const counts = document.querySelectorAll('.summary-count')
    expect([...counts].map((c) => c.textContent)).toEqual(['0', '1', '0'])
  })

  it('reports a failure instead of an empty summary', async () => {
    vi.mocked(api.listExamples).mockRejectedValueOnce(new Error('database is locked'))
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
  })

  it('lists starred expressions and words in short form, and only those', async () => {
    const stars: Stars = { expressions: ['on the fence'], words: ['mitigate'] }
    render(<SummaryTab sessionId={3} content={content} stars={stars} />)
    await screen.findByText("I'm on the fence about the offer.")

    const list = document.querySelector('.starred-list')!
    expect(list).toHaveTextContent('on the fence')
    expect(list).toHaveTextContent('undecided')
    expect(list).toHaveTextContent('mitigate')
    expect(list).toHaveTextContent('make less severe')
    expect(list).not.toHaveTextContent('a moving target')
    expect(list).not.toHaveTextContent('ubiquitous')
    expect(list).not.toHaveTextContent('We mitigated it.')
    expect(document.querySelector('.summary-count')).toHaveTextContent('2')
  })
})
