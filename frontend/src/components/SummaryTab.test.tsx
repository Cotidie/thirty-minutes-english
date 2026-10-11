import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Example, Reading, SessionContent, Stars } from '../types'
import { SummaryTab } from './SummaryTab'

vi.mock('../api', () => ({ api: { listExamples: vi.fn(), listReadings: vi.fn() } }))

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
  vi.mocked(api.listReadings).mockResolvedValue([reading])
})

describe('SummaryTab', () => {
  it('shows the sentences made and what was corrected, for this session only', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} note="" />)

    expect(await screen.findByText("I'm on the fence about the offer.")).toBeInTheDocument()
    expect(screen.getByText(/That's how a native speaker would say it/)).toBeInTheDocument()
    expect(vi.mocked(api.listExamples)).toHaveBeenCalledWith(3)
    expect(screen.getByText('verified')).toBeInTheDocument()
    expect(screen.getByText('twice as long')).toBeInTheDocument()
    expect(screen.getByText('phrasing')).toBeInTheDocument()
    expect(screen.getByText(/got it on the retry/)).toBeInTheDocument()

    expect(vi.mocked(api.listReadings)).toHaveBeenCalledWith(3)
  })

  it('puts the note first, line breaks and all', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} note={'hedge 발음 다시\nask about pauses'} />)
    await screen.findByText("I'm on the fence about the offer.")

    const first = document.querySelector('.summary-section')!
    expect(first).toHaveTextContent('Notes')
    expect(first.querySelector('.summary-note')!.textContent).toBe('hedge 발음 다시\nask about pauses')
  })

  it('points to the Notes box while the note is blank', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} note={'  \n'} />)
    expect(await screen.findByText(/Nothing noted/)).toBeInTheDocument()
    expect(document.querySelector('.summary-note')).toBeNull()
  })

  it('counts each section', async () => {
    render(<SummaryTab sessionId={3} content={content} stars={none} note="" />)
    await screen.findByText("I'm on the fence about the offer.")
    const counts = document.querySelectorAll('.summary-count')
    expect([...counts].map((c) => c.textContent)).toEqual(['0', '1', '2'])
  })

  it('tells a clean read apart from never having read aloud', async () => {
    vi.mocked(api.listReadings).mockResolvedValue([])
    const { unmount } = render(<SummaryTab sessionId={3} content={content} stars={none} note="" />)
    expect(await screen.findByText(/No paragraph read aloud yet/)).toBeInTheDocument()
    unmount()

    vi.mocked(api.listReadings).mockResolvedValue([{ ...reading, corrections: [] }])
    render(<SummaryTab sessionId={3} content={content} stars={none} note="" />)
    expect(await screen.findByText(/Clean read/)).toBeInTheDocument()
  })

  it('reports a failure instead of an empty summary', async () => {
    vi.mocked(api.listExamples).mockRejectedValueOnce(new Error('database is locked'))
    render(<SummaryTab sessionId={3} content={content} stars={none} note="" />)
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
  })

  it('lists starred expressions and words in short form, and only those', async () => {
    const stars: Stars = { expressions: ['on the fence'], words: ['mitigate'] }
    render(<SummaryTab sessionId={3} content={content} stars={stars} note="" />)
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
