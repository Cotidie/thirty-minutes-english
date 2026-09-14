import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Ask } from '../types'
import { AsksPage } from './AsksPage'

vi.mock('../api', () => ({ api: { askCards: vi.fn() } }))

const withCard: Ask = {
  id: 2,
  created_at: '2026-09-14T09:00:00Z',
  session_id: 3,
  user_text: '눈치 좀 챙기라는 말',
  coach_text: 'Read the room. Read the room. Friends or coworkers.',
  seconds: 12,
  card: {
    asked: '눈치 좀 챙겨',
    english: 'Read the room.',
    alternatives: ['Take a hint (blunter)'],
    note: 'Friends or coworkers, never to a manager.',
  },
}

const withoutCard: Ask = {
  id: 1,
  created_at: '2026-09-14T08:00:00Z',
  session_id: 3,
  user_text: 'uh, how do you say',
  coach_text: 'Sorry, say that again?',
  seconds: 4,
  card: null,
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AsksPage />
    </MemoryRouter>,
  )
}

beforeEach(() => vi.mocked(api.askCards).mockClear())

describe('AsksPage', () => {
  it('shows the expression, its alternatives, and the transcript behind it', async () => {
    vi.mocked(api.askCards).mockResolvedValue([withCard])
    renderAt('/asks?session_id=3')

    expect(await screen.findByText('Read the room.')).toBeInTheDocument()
    expect(screen.getByText('눈치 좀 챙겨')).toBeInTheDocument()
    expect(screen.getByText('Take a hint (blunter)')).toBeInTheDocument()
    expect(screen.getByText(/never to a manager/)).toBeInTheDocument()

    expect(screen.queryByText('Transcript')).not.toBeInTheDocument()
    expect(screen.queryByText(/Read the room\. Read the room\./)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the session' })).toHaveAttribute('href', '/s/3')
  })

  it('asks for that session only, or for everything from the home entry', async () => {
    vi.mocked(api.askCards).mockResolvedValue([])
    renderAt('/asks?session_id=3')
    expect(await screen.findByText(/Nothing asked yet/)).toBeInTheDocument()
    expect(vi.mocked(api.askCards)).toHaveBeenCalledWith(3)

    renderAt('/asks')
    expect(vi.mocked(api.askCards)).toHaveBeenLastCalledWith(undefined)
  })

  it('keeps a round that never reached an answer', async () => {
    vi.mocked(api.askCards).mockResolvedValue([withoutCard])
    renderAt('/asks')
    expect(await screen.findByText(/No answer landed/)).toBeInTheDocument()
    expect(screen.getByText('uh, how do you say')).toBeInTheDocument()
  })

  it('reports a failure instead of an empty list', async () => {
    vi.mocked(api.askCards).mockRejectedValueOnce(new Error('database is locked'))
    renderAt('/asks')
    expect(await screen.findByText(/database is locked/)).toBeInTheDocument()
  })
})
