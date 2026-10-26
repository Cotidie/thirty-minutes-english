import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { TopicEntry, TopicLibrary } from '../types'
import { TopicsPanel } from './TopicsPanel'

vi.mock('../api', () => ({ api: { topicLibrary: vi.fn() } }))

const topic = (over: Partial<TopicEntry>): TopicEntry => ({
  id: 1,
  text: 't',
  category: 'cs',
  added_at: '2026-10-26T00:00:00+00:00',
  news_days: [],
  sessions: [],
  ...over,
})

const library: TopicLibrary = {
  topics: [
    topic({ id: 1, text: 'Why databases still run the world', category: 'cs' }),
    topic({ id: 2, text: 'Mass protests sweeping Europe', category: 'news', news_days: ['2026-10-26'], sessions: [12] }),
    topic({ id: 3, text: 'why cities are bringing back trams', category: 'typed', sessions: [22] }),
  ],
  labels: { news: 'In the news', cs: 'Computer science', typed: 'Typed in' },
}

beforeEach(() => {
  vi.mocked(api.topicLibrary).mockResolvedValue(library)
})

function renderPanel() {
  render(
    <MemoryRouter>
      <TopicsPanel />
    </MemoryRouter>,
  )
}

function shown() {
  return screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
}

it('lists every topic newest first with its category and count', async () => {
  renderPanel()
  await screen.findByText('Why databases still run the world')
  expect(shown()).toEqual(['why cities are bringing back trams', 'Mass protests sweeping Europe', 'Why databases still run the world'])
  expect(screen.getByText('3 of 3')).toBeInTheDocument()
  expect(screen.getByText('Typed in', { selector: '.topic-category' })).toBeInTheDocument()
})

it('searches and filters by category and by use', async () => {
  renderPanel()
  await screen.findByText('Why databases still run the world')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'TRAMS' } })
  expect(shown()).toEqual(['why cities are bringing back trams'])
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'news' } })
  expect(shown()).toEqual(['Mass protests sweeping Europe'])
  fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'all' } })
  fireEvent.change(screen.getByLabelText('Used'), { target: { value: 'unused' } })
  expect(shown()).toEqual(['Why databases still run the world'])
})

it('says when a topic led the news and links the sessions written on it', async () => {
  renderPanel()
  await screen.findByText('Why databases still run the world')
  expect(screen.getByText(/In the news on/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Session 12' })).toHaveAttribute('href', '/s/12')
  expect(screen.getByRole('link', { name: 'Session 22' })).toHaveAttribute('href', '/s/22')
  expect(screen.getByText('Not used yet')).toBeInTheDocument()
})

it('says so when the topics do not load', async () => {
  vi.mocked(api.topicLibrary).mockRejectedValue(new Error('500 Internal Server Error'))
  renderPanel()
  expect(await screen.findByText(/Could not load the topics: 500/)).toBeInTheDocument()
})
