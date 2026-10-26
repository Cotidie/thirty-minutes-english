import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { JobStatus } from '../lib/progress'
import { HomePage } from './HomePage'

vi.mock('../api', () => ({
  api: { topics: vi.fn(), refreshTopics: vi.fn(), listSessions: vi.fn(), listJobs: vi.fn(), getJob: vi.fn(), cancelJob: vi.fn() },
}))

const running: JobStatus = {
  id: 'abc123',
  topic: 'Science fiction that predicted real technology',
  status: 'running',
  stage: 'starting',
  searches: 0,
  activity: '',
  input_tokens: 0,
  output_tokens: 0,
  pictures_done: 0,
  pictures_total: 0,
  elapsed_seconds: 10,
  stage_elapsed_seconds: 10,
  stage_expected_seconds: 10,
  expected_seconds: 150,
  session_id: null,
  error: null,
}

beforeEach(() => {
  vi.mocked(api.topics).mockResolvedValue({ topics: [], pending: false, error: null, labels: {} })
  vi.mocked(api.listSessions).mockResolvedValue([])
  vi.mocked(api.getJob).mockResolvedValue(running)
})

function renderHome() {
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

describe('HomePage', () => {
  it('picks up a generation still running on the server', async () => {
    vi.mocked(api.listJobs).mockResolvedValue([running])
    renderHome()

    expect(await screen.findByRole('progressbar', { name: 'Generation progress' })).toBeInTheDocument()
    expect(screen.getByText('Reading the brief')).toBeInTheDocument()
    expect(screen.getByText(running.topic)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Writing…' })).toBeDisabled()
  })

  it('shows a failed generation with its error until it is closed', async () => {
    vi.mocked(api.listJobs).mockResolvedValue([{ ...running, status: 'failed', error: 'claude timed out after 600s' }])
    vi.mocked(api.cancelJob).mockResolvedValue({ ...running, status: 'failed' })
    renderHome()

    expect(await screen.findByRole('alert')).toHaveTextContent('claude timed out after 600s')
    expect(screen.getByRole('button', { name: 'Generate session' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(api.cancelJob).toHaveBeenCalledWith(running.id)
  })

  it('shows no progress when nothing is running', async () => {
    vi.mocked(api.listJobs).mockResolvedValue([])
    renderHome()

    expect(await screen.findByRole('button', { name: 'Generate session' })).toBeEnabled()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
