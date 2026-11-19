import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Example, SessionContent, Stars, Summary } from '../types'
import { SummaryTab } from './SummaryTab'

vi.mock('../api', () => ({ api: { listExamples: vi.fn(), listReadings: vi.fn(), listSummaries: vi.fn() } }))

const content: SessionContent = {
  topic: 'Twins',
  expressions: [
    { id: 11, phrase: 'a moving target', meaning: 'something that keeps changing', usage_note: '', examples: [] },
    { id: 12, phrase: 'on the fence', meaning: 'undecided', usage_note: '', examples: [] },
  ],
  article: {
    title: 'Twins',
    paragraphs: [
      { id: 1, text: 'Upkeep is what actually pays for a twin.' },
      { id: 2, text: 'A modest twin delivers more value than a grand one.' },
    ],
    questions: [],
  },
  vocabulary: [
    { id: 41, word: 'mitigate', pos: 'verb', definition: 'make less severe', example: 'We mitigated it.' },
    { id: 42, word: 'ubiquitous', pos: 'adjective', definition: 'present everywhere', example: 'Phones are.' },
  ],
}

const none: Stars = { expressions: [], words: [] }

const example: Example = {
  id: 9,
  created_at: '',
  vocabulary_id: 41,
  user_text: 'We mitigated the delay.',
  coach_text: "We mitigated the delay. That's how a native speaker would say it.",
  seconds: 11,
}

const summary = (over: Partial<Summary>): Summary => ({
  id: 4,
  created_at: '',
  paragraph_id: 2,
  user_text: 'small ones win',
  seconds: 8,
  status: 'done',
  feedback: { missed: [], fixes: [], summary: 'Small twins pay off.' },
  error: null,
  speaker: 'jo',
  mine: true,
  ...over,
})

beforeEach(() => {
  vi.mocked(api.listExamples).mockResolvedValue([example])
  vi.mocked(api.listSummaries).mockResolvedValue([])
})

describe('SummaryTab', () => {
  it('shows the sentences made, for this session only', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)

    expect(await screen.findByText("We mitigated the delay.")).toBeInTheDocument()
    expect(screen.getByText(/That's how a native speaker would say it/)).toBeInTheDocument()
    expect(vi.mocked(api.listExamples)).toHaveBeenCalledWith(3)
  })

  it('labels each sentence with the word it was made with', async () => {
    vi.mocked(api.listExamples).mockResolvedValueOnce([example, { ...example, id: 10, vocabulary_id: 42, user_text: 'Phones are ubiquitous now.' }])
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText('Phones are ubiquitous now.')).toBeInTheDocument()
    const labels = [...document.querySelectorAll('.summary-cards')[0].querySelectorAll('.summary-card-label')].map((l) => l.textContent)
    expect(labels).toEqual(['mitigate', 'ubiquitous'])
  })

  it('leaves the note to its button and the read-aloud marks to the article', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText("We mitigated the delay.")
    const titles = [...document.querySelectorAll('.summary-title')].map((t) => t.firstChild?.textContent)
    expect(titles).toEqual(['Starred', 'Sentences you made', 'Paragraphs summed up'])
    expect(vi.mocked(api.listReadings)).not.toHaveBeenCalled()
  })

  it('counts each section', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText("We mitigated the delay.")
    const counts = document.querySelectorAll('.summary-count')
    expect([...counts].map((c) => c.textContent)).toEqual(['0', '1', '0'])
  })

  it('names each summary by who said it and the opening words of its paragraph', async () => {
    vi.mocked(api.listSummaries).mockResolvedValueOnce([
      summary({ id: 4, paragraph_id: 2, user_text: 'small ones win' }),
      summary({ id: 5, paragraph_id: 1, user_text: 'upkeep pays', mine: false, speaker: 'mina' }),
    ])
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText('small ones win')).toBeInTheDocument()
    expect(screen.getByText('You · A modest twin delivers…')).toBeInTheDocument()
    expect(screen.getByText('mina · Upkeep is what actually…')).toBeInTheDocument()
  })

  it('says where the feedback of each summary is', async () => {
    vi.mocked(api.listSummaries).mockResolvedValueOnce([
      summary({ id: 4, user_text: 'done one' }),
      summary({ id: 5, user_text: 'judging one', status: 'judging', feedback: null }),
      summary({ id: 6, user_text: 'failed one', status: 'failed', feedback: null, error: 'feedback failed: down' }),
    ])
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText('done one')
    expect(screen.getByText('Small twins pay off.')).toBeInTheDocument()
    expect(screen.getByText('Waiting for feedback…')).toBeInTheDocument()
    expect(screen.getByText('No feedback: judge it again in the Article tab.')).toBeInTheDocument()
  })

  it('reports a failure instead of an empty summary', async () => {
    vi.mocked(api.listExamples).mockRejectedValueOnce(new Error('database is locked'))
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
  })

  it('lists starred expressions and words in short form, and only those', async () => {
    const stars: Stars = { expressions: [12], words: [41] }
    render(<SummaryTab sessionId={3} content={content} stars={stars} />)
    await screen.findByText("We mitigated the delay.")

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
