import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { JobStatus } from '../lib/progress'
import type { TopicEntry, TopicLibrary } from '../types'
import { TopicsPanel } from './TopicsPanel'

vi.mock('../api', () => ({
  api: { topicLibrary: vi.fn(), deleteTopic: vi.fn(), listJobs: vi.fn(), startGeneration: vi.fn(), getJob: vi.fn(), cancelJob: vi.fn() },
}))

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

const RUNNING: JobStatus = {
  id: 'job-1',
  topic: 'Why databases still run the world',
  status: 'running',
  stage: 'searching',
  searches: 2,
  activity: 'Searching "silk road trade"',
  input_tokens: 12300,
  output_tokens: 850,
  pictures_done: 0,
  pictures_total: 0,
  elapsed_seconds: 42,
  stage_elapsed_seconds: 5,
  stage_expected_seconds: 30,
  expected_seconds: 150,
  session_id: null,
  error: null,
}

beforeEach(() => {
  vi.mocked(api.topicLibrary).mockReset().mockResolvedValue(library)
  vi.mocked(api.listJobs).mockReset().mockResolvedValue([])
  vi.mocked(api.startGeneration).mockReset().mockResolvedValue(RUNNING)
  vi.mocked(api.getJob).mockReset().mockResolvedValue(RUNNING)
  vi.mocked(api.cancelJob).mockReset().mockResolvedValue(RUNNING)
})

function renderPanel() {
  render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<TopicsPanel />} />
        <Route path="/s/:id" element={<p>The new session</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

const createOn = (text: string) => screen.findByRole('button', { name: `Create a session on ${text}` })

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

it('offers delete only on the topics no session was written on', async () => {
  renderPanel()
  await screen.findByText('Why databases still run the world')
  expect(screen.getByRole('button', { name: 'Delete Why databases still run the world' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete Mass protests sweeping Europe' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete why cities are bringing back trams' })).not.toBeInTheDocument()
})

it('deletes a topic after a confirm', async () => {
  vi.mocked(api.deleteTopic).mockResolvedValue(undefined)
  renderPanel()
  await screen.findByText('Why databases still run the world')
  fireEvent.click(screen.getByRole('button', { name: 'Delete Why databases still run the world' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete for good' }))
  await waitFor(() => expect(shown()).toEqual(['why cities are bringing back trams', 'Mass protests sweeping Europe']))
  expect(api.deleteTopic).toHaveBeenCalledWith(1)
  expect(screen.getByText('2 of 2')).toBeInTheDocument()
})

it('puts the category on the line under the topic, so the title line only has to fit the buttons', async () => {
  renderPanel()
  const heading = await screen.findByRole('heading', { name: 'Why databases still run the world' })
  const row = heading.closest('li') as HTMLElement
  expect(within(row).getByText('Computer science').closest('p')).toHaveClass('db-meta')
})

it('starts a session on a topic from its row, and opens it once it is saved', async () => {
  vi.mocked(api.getJob).mockResolvedValue({ ...RUNNING, session_id: 42 })
  renderPanel()
  await userEvent.click(await createOn('Why databases still run the world'))
  expect(api.startGeneration).toHaveBeenCalledWith('Why databases still run the world')
  expect(await screen.findByRole('progressbar', { name: 'Generation progress' })).toBeInTheDocument()
  expect(await screen.findByText('The new session', {}, { timeout: 2500 })).toBeInTheDocument()
})

it('offers another session on a topic already used', async () => {
  renderPanel()
  await userEvent.click(await createOn('Mass protests sweeping Europe'))
  expect(api.startGeneration).toHaveBeenCalledWith('Mass protests sweeping Europe')
})

it('starts one at a time, and cancelling frees the buttons again', async () => {
  renderPanel()
  await userEvent.click(await createOn('Why databases still run the world'))
  expect(await createOn('Mass protests sweeping Europe')).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(api.cancelJob).toHaveBeenCalledWith('job-1')
  expect(await createOn('Mass protests sweeping Europe')).toBeEnabled()
})

it('shows a session already being written when the page opens', async () => {
  vi.mocked(api.listJobs).mockResolvedValue([RUNNING])
  renderPanel()
  expect(await screen.findByRole('progressbar', { name: 'Generation progress' })).toBeInTheDocument()
  expect(await createOn('Why databases still run the world')).toBeDisabled()
})

it('says so when a session cannot be started, and the buttons stay free', async () => {
  vi.mocked(api.startGeneration).mockRejectedValue(new Error('503 Service Unavailable'))
  renderPanel()
  await userEvent.click(await createOn('Why databases still run the world'))
  expect(await screen.findByText('Could not create the session: 503 Service Unavailable')).toBeInTheDocument()
  expect(await createOn('Why databases still run the world')).toBeEnabled()
})
