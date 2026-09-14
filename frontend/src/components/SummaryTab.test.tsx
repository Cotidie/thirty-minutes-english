import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Ask, Reading, SessionContent, Stars } from '../types'
import { SummaryTab } from './SummaryTab'

vi.mock('../api', () => ({ api: { askCards: vi.fn(), readingCorrections: vi.fn() } }))

const ask: Ask = {
  id: 2,
  created_at: '2026-09-14T09:00:00Z',
  session_id: 3,
  user_text: '눈치 좀 챙기라는 말',
  coach_text: 'Read the room.',
  seconds: 12,
  card: {
    asked: '눈치 좀 챙겨',
    english: 'Read the room.',
    alternatives: ['Take a hint (blunter)'],
    note: 'Friends or coworkers, never to a manager.',
  },
}

const reading: Reading = {
  id: 5,
  created_at: '2026-09-14T09:10:00Z',
  session_id: 3,
  paragraph: 'Researchers verified it.',
  user_text: 'researchers berified it',
  coach_text: 'Quick one: that was berified.',
  seconds: 31,
  corrections: [
    { kind: 'pronunciation', word: 'verified', heard: 'berified', fix: 'V, teeth on the lip', repeated_ok: true },
    { kind: 'phrasing', word: 'twice as long', heard: 'twice as / long', fix: 'one piece', repeated_ok: false },
  ],
}

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

beforeEach(() => {
  vi.mocked(api.askCards).mockResolvedValue([ask])
  vi.mocked(api.readingCorrections).mockResolvedValue([reading])
})

describe('SummaryTab', () => {
  it('shows both what was asked and what was corrected, for this session only', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)

    expect(await screen.findByText('Read the room.')).toBeInTheDocument()
    expect(screen.getByText('Take a hint (blunter)')).toBeInTheDocument()
    expect(screen.getByText('verified')).toBeInTheDocument()
    expect(screen.getByText('twice as long')).toBeInTheDocument()
    expect(screen.getByText('phrasing')).toBeInTheDocument()
    expect(screen.getByText(/got it on the retry/)).toBeInTheDocument()

    expect(vi.mocked(api.askCards)).toHaveBeenCalledWith(3)
    expect(vi.mocked(api.readingCorrections)).toHaveBeenCalledWith(3)
  })

  it('counts each section', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    await screen.findByText('Read the room.')
    const counts = document.querySelectorAll('.summary-count')
    expect([...counts].map((c) => c.textContent)).toEqual(['0', '1', '2'])
  })

  it('tells a clean read apart from never having read aloud', async () => {
    vi.mocked(api.askCards).mockResolvedValue([])
    vi.mocked(api.readingCorrections).mockResolvedValue([])
    const { unmount } = render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText(/No paragraph read aloud yet/)).toBeInTheDocument()
    unmount()

    vi.mocked(api.readingCorrections).mockResolvedValue([{ ...reading, corrections: [] }])
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText(/Clean read/)).toBeInTheDocument()
  })

  it('reports a failure instead of an empty summary', async () => {
    vi.mocked(api.askCards).mockRejectedValueOnce(new Error('database is locked'))
    render(<SummaryTab sessionId={3} content={content} stars={none} />)
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
  })

  it('lists starred expressions and words in short form, and only those', async () => {
    const stars: Stars = { expressions: ['on the fence'], words: ['mitigate'] }
    render(<SummaryTab sessionId={3} content={content} stars={stars} />)
    await screen.findByText('Read the room.')

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
